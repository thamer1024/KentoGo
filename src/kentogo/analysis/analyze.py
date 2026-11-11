"""Analyze a game with KataGo in KentoGo's way: every position, again when asked, and the played moves.

The steps (see analyze_game):

1. Every node of the tree (branches too) without saved analysis data (KT) is analyzed with the
   engine's max_visits (or fast_visits), at KaTrain's priority for a game, with KaTrain's time limit
   (the engine's max_time), as KaTrain analyzes a game that it opens. Saved analysis data is used as it is.
2. When reanalyze is on, the nodes are analyzed again with more visits (reanalyze_visits, or the
   fewest visits of any node, counting the saved data, plus max_visits): only the moves that lost
   reanalyze_threshold points or more when mistakes_only is on, and only the positions that the
   moves from move_from to move_to need.
3. The played moves are read in the position before them (see analysis.played_moves), so that the
   loss of a move is the best move's score minus the played move's score in the same position.
   They are read with the visits and the time limit of the first analysis at most, even when KaTrain
   read the position more deeply: only the moves that are read deeply need more. When moves are read deeply (DeepTargets are given), only the played moves that may be read deeply
   are read: those that lost at least PLAYED_READ_SHARE of the smallest loss of their color, by the
   loss known so far (KaTrain's way for data that KaTrain wrote), not in a decided position. The other
   moves keep the loss known so far: they never become problems, and reading them all takes about as
   long as the first analysis.
4. The moves that can become problems (DeepTargets: the user's moves that lost at least the smallest
   loss of a problem, the opponent's moves that lost at least the loss of a punishment chance, not in
   a position where the game was already decided, by the quiz's rule; an opponent's move only when the
   user's reply did not punish it, see DeepTargets.reply_loss, and not when it only left the same point
   again, see mistakes.extract) are read deeply: the positions before and
   after them with the deep visits, and the played move again.
   At most max_moves of them are read in a game, the biggest losses first, but the opponent's moves
   take at most half of them: the user's mistakes come first.
   The moves that still lose that much are the game's deep_nodes; KentoGo's own data (KGD) is written
   for them only, so the small changes of the other moves do not make the file bigger.
5. KentoGo's own readings of the deep nodes, with the same visits (see analysis.kentogo_reading), each
   only when its setting is on, as they take long; they are the material of features that come later:
   the position after the best move (area_readings), the readings with a pass (pass_readings), the
   sequences until the place settles (settled_lines, see analysis.settled_lines), and the last position
   of the game (end_reading, for counting problems).

The analysis again (2) and the deep reading (4, 5) have no time limit, as KaTrain's re-analysis.
A node that KataGo could not analyze is asked again (retries times). The answer for a position is
kept in that position only. KaTrain's own way (two separate analyses for a loss,
the answer of a position changing the one before it) is not used: a game that needs it can be
analyzed with KaTrain itself.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pysgf import GoNode

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.game_analysis import (
    GAME_PRIORITY,
    REANALYSIS_PRIORITY,
    Engine,
    EngineValues,
    GameAnalysis,
    Progress,
    analysis_step,
    analyze_with_retries,
    first_nodes,
    load_saved_analyses,
)
from kentogo.analysis.kentogo_reading import BEST_READINGS, PASS_READINGS, best_move, read_end, read_tenuki
from kentogo.analysis.played_moves import needs_reading, played_move_loss, read_played_moves
from kentogo.analysis.query import QuerySettings
from kentogo.analysis.settled_lines import LineSettings, read_lines
from kentogo.common.handicap import from_start

FIRST_STEP = "first"  # The analysis of the nodes without saved data.
REANALYSIS_STEP = "again"  # The analysis again (KaTrain's "Re-analyze game").
DEEP_STEP = "deep"  # The deep reading of the moves that can become problems.
END_OF_GAME = 100_000  # The end of the range of moves when move_to is 0.
# A played move is read in the position before it when it lost at least this share of the smallest loss
# of a move read deeply (the loss can change when it is read, so a little less than that loss is read too).
PLAYED_READ_SHARE = 2 / 3


@dataclass(frozen=True)
class DeepTargets:
    """Which moves are read deeply (see the module's docstring).

    Attributes:
        losses: The smallest loss of a move read deeply, by color ("B" and "W"); a color that is
            missing is not read deeply.
        visits: The visits of the deep reading.
        decided: Tells whether a position is decided, from black's winrate and score lead before the move
            (see mistakes.selection.Selection.is_decided); a move in a decided position is not read deeply.
        max_moves: The most moves read deeply in a game, the user's mistakes first (see chosen_deep_candidates;
            0: no limit).
        my_colors: The colors of the user's moves ("B" and "W" when the user's color is not known).
        reply_loss: An opponent's move is read deeply only when the user's reply (its first child) lost at
            least this many points: the user did not punish it (the quiz's punish_my_loss).
        handicap: True for a game with handicap stones: then decided is given the lead gained since the start
            and no winrate (see common.handicap).
    """

    losses: dict[str, float]
    visits: int
    decided: Callable[[float | None, float | None], bool] = field(default=lambda _winrate, _lead: False, compare=False)
    max_moves: int = 0
    my_colors: frozenset[str] = frozenset({"B", "W"})
    reply_loss: float = 0.0
    handicap: bool = False


def analyze_game(
    engine: Engine,
    root: GoNode,
    settings: AnalysisSettings,
    values: EngineValues,
    progress: Progress,
    targets: DeepTargets | None = None,
) -> GameAnalysis:
    """Analyze a game: the saved data, the first step, the analysis again when it is on, the played moves,
    and the deep reading of the moves that can become problems (when targets are given).

    Args:
        engine: KataGo.
        root: The root node of the game.
        settings: The settings of the analysis.
        values: The engine settings that the analysis uses.
        progress: Called after each answer, in KataGo's thread, with the step, the answers and the queries.
        targets: Which moves are read deeply, or None for none.

    Returns:
        The analyses of the nodes.
    """
    game = GameAnalysis(root)
    load_saved_analyses(game)
    visits = settings.fast_visits if settings.fast else values.max_visits
    first = analysis_step(game, QuerySettings(visits, values.wide_root_noise, GAME_PRIORITY, max_time=values.max_time))
    analyze_with_retries(engine, game, first_nodes(game), first, _step(progress, FIRST_STEP), settings.retries)
    if settings.reanalyze:
        again_visits = settings.reanalyze_visits or reanalysis_visits(game, values.max_visits)
        again = analysis_step(game, QuerySettings(again_visits, values.wide_root_noise, REANALYSIS_PRIORITY))
        nodes = reanalysis_nodes(game, settings)
        analyze_with_retries(engine, game, nodes, again, _step(progress, REANALYSIS_STEP), settings.retries)
    first_values = replace(values, max_visits=visits)  # Read as deeply as the first analysis, at most.
    read_played_moves(engine, game, first_values, progress, settings.retries, played_nodes(game, targets))
    if targets is not None:
        read_deeply(engine, game, values, progress, settings, targets)
    return game


def read_deeply(
    engine: Engine,
    game: GameAnalysis,
    values: EngineValues,
    progress: Progress,
    settings: AnalysisSettings,
    targets: DeepTargets,
) -> None:
    """Read the moves that can become problems deeply, and keep those that still lose enough as deep_nodes.

    The positions before and after each move are analyzed with the deep visits (unless they were read
    that deeply already), and the played move is read again in the position before it with those visits,
    so that the best move and the played move are compared at the same depth. For an opponent's move,
    the user's reply is read again too: it tells how much the user lost by not punishing it.
    """
    retries = settings.retries
    nodes = chosen_deep_candidates(game, targets)
    positions = []
    for node in nodes:
        for position in (node.parent, node):
            if position not in positions and _node_visits(game, position) < targets.visits:
                positions.append(position)
    deep = analysis_step(game, QuerySettings(targets.visits, values.wide_root_noise, REANALYSIS_PRIORITY))
    analyze_with_retries(engine, game, positions, deep, _step(progress, DEEP_STEP), retries)
    deep_values = replace(values, max_visits=targets.visits, max_time=0.0)  # The deep visits, no time limit.
    chosen = {id(node) for node in nodes}
    replies = [node.children[0] for node in nodes if not _is_mine(node, targets) and node.children]
    replies = [reply for reply in replies if id(reply) not in chosen]  # A reply read deeply itself is read once.
    read_played_moves(engine, game, deep_values, progress, retries, nodes + replies)
    game.deep_nodes = [node for node in deep_candidates(game, targets) if id(node) in chosen]
    game.deep_visits = targets.visits
    names = (BEST_READINGS if settings.area_readings else ()) + (PASS_READINGS if settings.pass_readings else ())
    noise = values.wide_root_noise
    read_tenuki(engine, game, targets.visits, noise, REANALYSIS_PRIORITY, progress, retries, names)
    if settings.settled_lines:
        lines = LineSettings(
            settings.settle_radius, settings.settle_change, settings.settle_step, settings.settle_max_moves
        )
        read_lines(engine, game, targets.visits, noise, REANALYSIS_PRIORITY, progress, retries, lines)
    if settings.end_reading:
        read_end(engine, game, targets.visits, noise, REANALYSIS_PRIORITY, progress, retries)


def played_nodes(game: GameAnalysis, targets: DeepTargets | None) -> list[GoNode]:
    """Return the nodes whose played move is read in the position before it.

    They are the nodes that need it (see analysis.played_moves.needs_reading); when moves are read deeply,
    only those whose move lost at least PLAYED_READ_SHARE of the smallest loss of its color, not in a
    decided position (see the module's docstring).
    """
    nodes = [node for node in game.nodes if needs_reading(game, node)]
    if targets is None:
        return nodes
    losses = {color: loss * PLAYED_READ_SHARE for color, loss in targets.losses.items()}
    rough = replace(targets, losses=losses, reply_loss=targets.reply_loss * PLAYED_READ_SHARE)
    return [node for node in nodes if _is_candidate(game, node, rough)]


def deep_candidates(game: GameAnalysis, targets: DeepTargets) -> list[GoNode]:
    """Return the nodes whose move lost at least the smallest loss of its color, in a position that was not
    decided (see DeepTargets), in the order of the game."""
    return [node for node in game.nodes if _is_candidate(game, node, targets)]


def chosen_deep_candidates(game: GameAnalysis, targets: DeepTargets) -> list[GoNode]:
    """Return the deep candidates that are read deeply, in the order of the game (all when max_moves is 0).

    The biggest losses are taken, but the user's mistakes come first: the opponent's moves take at most
    half of max_moves (rounded down), so at least half are the user's mistakes when there are enough of them.
    Of two equal losses, the user's move and then the earlier move is taken.
    """
    found = deep_candidates(game, targets)
    if targets.max_moves <= 0:
        return found
    order = sorted(found, key=lambda node: (-(played_move_loss(game, node) or 0.0), not _is_mine(node, targets)))
    theirs_left = targets.max_moves // 2
    chosen: set[int] = set()
    for node in order:
        if len(chosen) == targets.max_moves:
            break
        if not _is_mine(node, targets):
            if theirs_left == 0:
                continue
            theirs_left -= 1
        chosen.add(id(node))
    return [node for node in found if id(node) in chosen]


def _is_mine(node: GoNode, targets: DeepTargets) -> bool:
    """True if the node's move is the user's."""
    return node.move is not None and node.move.player in targets.my_colors


def _is_candidate(game: GameAnalysis, node: GoNode, targets: DeepTargets) -> bool:
    """True if a node's move lost at least the smallest loss of its color, in a position that was not decided,
    and, for an opponent's move, the user's reply did not punish it and the opponent did not only leave the
    same point again (see _left_again)."""
    move = node.move
    before = game.analysis(node.parent) if node.parent is not None else None
    if move is None or before is None:
        return False
    if _is_decided(game, node, before, targets):
        return False
    loss = played_move_loss(game, node)
    if loss is None or loss < targets.losses.get(move.player, math.inf):
        return False
    return _is_mine(node, targets) or (_not_punished(game, node, targets) and not _left_again(game, node))


def _is_decided(game: GameAnalysis, node: GoNode, before: dict, targets: DeepTargets) -> bool:
    """True if the game was decided before a node's move (before: the analysis of the position before it)."""
    values = before["root"].get("winrate"), before["root"].get("scoreLead")
    if targets.handicap:
        start = game.analysis(node.root)
        values = from_start(*values, start["root"].get("scoreLead") if start is not None else None)
    return targets.decided(*values)


def _not_punished(game: GameAnalysis, node: GoNode, targets: DeepTargets) -> bool:
    """True if the user's reply to an opponent's move (the node's first child) lost at least reply_loss points."""
    reply = node.children[0] if node.children else None
    if reply is None or reply.move is None or not _is_mine(reply, targets):
        return False
    loss = played_move_loss(game, reply)
    return loss is not None and loss >= targets.reply_loss


def _left_again(game: GameAnalysis, node: GoNode) -> bool:
    """True if the best move before a node's move was already the best move before the same player's move before.

    The player then only left the same point again: the loss of the move was not made by it, so it is no
    punishment chance (the same rule as mistakes.extract). The best moves are those of the analysis so far.
    """
    before = node.parent.parent if node.parent is not None else None
    if before is None or before.move is None or before.move.player != node.move.player:
        return False
    best = best_move(game, node)
    return best is not None and best == best_move(game, before)


def reanalysis_visits(game: GameAnalysis, max_visits: int) -> int:
    """Return the fewest visits of any node, counting the visits of saved analysis data, plus max_visits.

    So the analysis again always reads more deeply than before (KaTrain counts saved data as 0 visits).
    """
    return min((_node_visits(game, node) for node in game.nodes), default=0) + max_visits


def _node_visits(game: GameAnalysis, node: GoNode) -> int:
    """Return the visits asked for a node, or the visits of its saved analysis data."""
    analysis = game.analysis(node)
    saved = analysis["root"].get("visits", 0) if analysis is not None else 0
    return max(game.visits.get(id(node), 0), saved)


def reanalysis_nodes(game: GameAnalysis, settings: AnalysisSettings) -> list[GoNode]:
    """Return the nodes analyzed again: with mistakes_only, those where the node's move or a move after it
    lost reanalyze_threshold points or more; and the positions that the moves of the range need (from the
    position before the first move to the one after the last move, in whichever order the range is given)."""
    low, high = _range(settings)
    return [
        node
        for node in game.nodes
        if (not settings.mistakes_only or _largest_loss(game, node) >= settings.reanalyze_threshold)
        and low - 1 <= node.depth <= high
    ]


def _largest_loss(game: GameAnalysis, node: GoNode) -> float:
    """Return the largest loss of the node's move and the moves after it (0 when not known)."""
    return max(played_move_loss(game, item) or 0 for item in [node, *node.children])


def _range(settings: AnalysisSettings) -> tuple[int, int]:
    """Return the range of moves analyzed again, the smaller first (the whole game when none is set)."""
    if not settings.move_from and not settings.move_to:
        return -1, END_OF_GAME
    ends = (settings.move_from, settings.move_to or END_OF_GAME)
    return min(ends), max(ends)


def _step(progress: Progress, step: str):
    """Return the progress of one step."""
    return lambda done, total: progress(step, done, total)
