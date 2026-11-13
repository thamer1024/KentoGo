"""Analyze a game with KataGo in KentoGo's way: every position, the played moves, and the possible problems.

The steps (see analyze_game):

1. Every node of the tree (branches too) without saved analysis data (KT) is analyzed with the
   analysis's fast_visits, but never fewer than katago.presets.MIN_FAST_VISITS (see first_visits: only
   to find the moves that can become problems; they are read deeply in step 3), at KaTrain's priority for
   a game, with KaTrain's time limit (the engine's max_time), as KaTrain analyzes a game that it opens.
   Saved analysis data is used as it is.
2. The played moves are read in the position before them (see analysis.played_moves), so that the
   loss of a move is the best move's score minus the played move's score in the same position.
   They are read with the visits and the time limit of the first analysis at most, even when KaTrain
   read the position more deeply: only the moves that are read deeply need more. When moves are read
   deeply (DeepTargets are given), only the played moves that may be read deeply are read: those that
   lost at least PLAYED_READ_SHARE of the smallest loss of their color, by the loss known so far
   (KaTrain's way for data that KaTrain wrote), not in a decided position. The other moves keep the loss
   known so far: they never become problems, and reading them all takes about as long as the first analysis.
3. The moves that can become problems (DeepTargets: the user's moves that lost at least the smallest
   loss of a problem, the opponent's moves that lost at least the loss of a punishment chance, not in
   a position where the game was already decided, by the quiz's rule; an opponent's move only when the
   user's reply did not punish it, see DeepTargets.reply_loss, and not when it only left the same point
   again, see mistakes.extract) are read deeply: the positions before and
   after them with the deep visits, and the played move again.
   At most max_moves of them are read in a game, the biggest losses first, but the opponent's moves
   take at most half of them: the user's mistakes come first.
   The moves that still lose that much are the game's deep_nodes.

The deep reading (3) has no time limit, as KaTrain's re-analysis. A node that KataGo could not analyze
is asked again (retries times). The answer for a position is kept in that position only. KaTrain's own
way (two separate analyses for a loss, the answer of a position changing the one before it) is not used:
a game that needs it can be analyzed with KaTrain itself.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pysgf import GoNode

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.game_analysis import (
    DEEP_PRIORITY,
    GAME_PRIORITY,
    Engine,
    EngineValues,
    GameAnalysis,
    Progress,
    analysis_step,
    analyze_with_retries,
    first_nodes,
    load_saved_analyses,
)
from kentogo.analysis.played_moves import needs_reading, played_move_loss, read_played_moves
from kentogo.analysis.query import QuerySettings
from kentogo.common.handicap import from_start
from kentogo.katago.presets import MIN_FAST_VISITS

FIRST_STEP = "first"  # The analysis of the nodes without saved data.
DEEP_STEP = "deep"  # The deep reading of the moves that can become problems.
# A played move is read in the position before it when it lost at least this share of the smallest loss
# of a move read deeply (the loss can change when it is read, so a little less than that loss is read too).
PLAYED_READ_SHARE = 2 / 3


@dataclass(frozen=True)
class DeepTargets:
    """Which moves are read deeply (see the module's docstring).

    Attributes:
        losses: The smallest loss of a problem, by color ("B" and "W"); a color that is missing is not
            read deeply.
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
        read_share: A move is read deeply when it lost this share of losses (and the user's reply this share of
            reply_loss) by the first analysis, whose losses are rough; after the deep reading, only the moves
            that lost the whole losses are the game's problem_nodes (see read_deeply).
    """

    losses: dict[str, float]
    visits: int
    decided: Callable[[float | None, float | None], bool] = field(default=lambda _winrate, _lead: False, compare=False)
    max_moves: int = 0
    my_colors: frozenset[str] = frozenset({"B", "W"})
    reply_loss: float = 0.0
    handicap: bool = False
    read_share: float = 1.0

    def scaled(self, share: float) -> DeepTargets:
        """Return the same targets with losses and reply_loss multiplied by share."""
        losses = {color: loss * share for color, loss in self.losses.items()}
        return replace(self, losses=losses, reply_loss=self.reply_loss * share)


def analyze_game(
    engine: Engine,
    root: GoNode,
    settings: AnalysisSettings,
    values: EngineValues,
    progress: Progress,
    targets: DeepTargets | None = None,
) -> GameAnalysis:
    """Analyze a game: the saved data, the first step, the played moves, and the deep reading of the moves that
    can become problems (when targets are given).

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
    visits = first_visits(settings)
    first = analysis_step(game, QuerySettings(visits, values.wide_root_noise, GAME_PRIORITY, max_time=values.max_time))
    analyze_with_retries(engine, game, first_nodes(game), first, _step(progress, FIRST_STEP), settings.retries)
    first_values = replace(values, max_visits=visits)  # Read as deeply as the first analysis, at most.
    read_played_moves(engine, game, first_values, progress, settings.retries, played_nodes(game, targets))
    if targets is not None:
        read_deeply(engine, game, values, progress, settings.retries, targets)
    return game


def first_visits(settings: AnalysisSettings) -> int:
    """Return the visits of the first analysis: fast_visits, but never fewer than MIN_FAST_VISITS.

    With fewer visits, KataGo's score of a move is too rough to find the mistakes that can become problems,
    so a low setting (KaTrain's fast_visits is often 25 or less) is raised to it.
    """
    return max(settings.fast_visits, MIN_FAST_VISITS)


def read_deeply(
    engine: Engine,
    game: GameAnalysis,
    values: EngineValues,
    progress: Progress,
    retries: int,
    targets: DeepTargets,
) -> None:
    """Read the moves that can become problems deeply, and keep the moves that lose enough as problem_nodes.

    The moves read deeply are chosen with the rough losses of the first analysis (see DeepTargets.read_share).
    After the reading, the moves of the game that lost the whole losses are the problem_nodes, and those of
    them that were read deeply are the deep_nodes.

    The positions before and after each move are analyzed with the deep visits (unless they were read
    that deeply already), and the played move is read again in the position before it with those visits,
    so that the best move and the played move are compared at the same depth. For an opponent's move,
    the user's reply is read again too: it tells how much the user lost by not punishing it.
    """
    nodes = chosen_deep_candidates(game, targets)
    positions = []
    for node in nodes:
        for position in (node.parent, node):
            if position not in positions and _node_visits(game, position) < targets.visits:
                positions.append(position)
    deep = analysis_step(game, QuerySettings(targets.visits, values.wide_root_noise, DEEP_PRIORITY))
    analyze_with_retries(engine, game, positions, deep, _step(progress, DEEP_STEP), retries)
    deep_values = replace(values, max_visits=targets.visits, max_time=0.0)  # The deep visits, no time limit.
    chosen = {id(node) for node in nodes}
    replies = [node.children[0] for node in nodes if not _is_mine(node, targets) and node.children]
    replies = [reply for reply in replies if id(reply) not in chosen]  # A reply read deeply itself is read once.
    read_played_moves(engine, game, deep_values, progress, retries, nodes + replies)
    game.problem_nodes = deep_candidates(game, targets)
    game.deep_nodes = [node for node in game.problem_nodes if id(node) in chosen]


def played_nodes(game: GameAnalysis, targets: DeepTargets | None) -> list[GoNode]:
    """Return the nodes whose played move is read in the position before it.

    They are the nodes that need it (see analysis.played_moves.needs_reading); when moves are read deeply,
    only those whose move lost at least PLAYED_READ_SHARE of the smallest loss of its color that is read
    deeply (DeepTargets.read_share of the losses), not in a decided position (see the module's docstring).
    """
    nodes = [node for node in game.nodes if needs_reading(game, node)]
    if targets is None:
        return nodes
    rough = targets.scaled(targets.read_share * PLAYED_READ_SHARE)
    return [node for node in nodes if _is_candidate(game, node, rough)]


def deep_candidates(game: GameAnalysis, targets: DeepTargets) -> list[GoNode]:
    """Return the nodes whose move lost at least the smallest loss of its color, in a position that was not
    decided (see DeepTargets), in the order of the game."""
    return [node for node in game.nodes if _is_candidate(game, node, targets)]


def chosen_deep_candidates(game: GameAnalysis, targets: DeepTargets) -> list[GoNode]:
    """Return the deep candidates that are read deeply, in the order of the game (all when max_moves is 0).

    The candidates are the moves that lost DeepTargets.read_share of the losses. The biggest losses are taken, but the user's mistakes come first: the opponent's moves take at most
    half of max_moves (rounded down), so at least half are the user's mistakes when there are enough of them.
    Of two equal losses, the user's move and then the earlier move is taken.
    """
    found = deep_candidates(game, targets.scaled(targets.read_share))
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
    best = _best_move(game, node)
    return best is not None and best == _best_move(game, before)


def _best_move(game: GameAnalysis, node: GoNode) -> str | None:
    """Return KataGo's best move (order 0) in the position before a node, or None."""
    analysis = game.analysis(node.parent)
    if analysis is None:
        return None
    return next((values["move"] for values in analysis["moves"].values() if values.get("order") == 0), None)


def _node_visits(game: GameAnalysis, node: GoNode) -> int:
    """Return the visits asked for a node, or the visits of its saved analysis data."""
    analysis = game.analysis(node)
    saved = analysis["root"].get("visits", 0) if analysis is not None else 0
    return max(game.visits.get(id(node), 0), saved)


def _step(progress: Progress, step: str):
    """Return the progress of one step."""
    return lambda done, total: progress(step, done, total)
