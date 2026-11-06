"""Analyze a game with KataGo in KentoGo's way: every position, again when asked, and the played moves.

The steps (see analyze_game):

1. Every node of the tree (branches too) without saved analysis data (KT) is analyzed with the
   engine's max_visits (or fast_visits), at KaTrain's priority for a game, without a time limit,
   so every position is read as deeply. Saved analysis data is used as it is.
2. When reanalyze is on, the nodes are analyzed again with more visits (reanalyze_visits, or the
   fewest visits of any node, counting the saved data, plus max_visits): only the moves that lost
   reanalyze_threshold points or more when mistakes_only is on, and only the positions that the
   moves from move_from to move_to need.
3. The played moves are read in the position before them (see analysis.played_moves), so that the
   loss of a move is the best move's score minus the played move's score in the same position.
4. The moves that can become problems (DeepTargets: the user's moves that lost at least the smallest
   loss of a problem, the opponent's moves that lost at least the loss of a punishment chance, not in
   a position where the game was already decided, by the quiz's rule) are read deeply: the positions before and after them with the deep visits, and the played move again.
   The moves that still lose that much are the game's deep_nodes; KentoGo's own data (KGD) is written
   for them only, so the small changes of the other moves do not make the file bigger.
5. KentoGo's own readings of the deep nodes, with the same visits (see analysis.kentogo_reading).

A node that KataGo could not analyze is asked again (retries times). The answer for a position is
kept in that position only. KaTrain's own way (two separate analyses for a loss, the time limit,
the answer of a position changing the one before it) is not used: a game that needs it can be
analyzed with KaTrain itself.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

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
from kentogo.analysis.kentogo_reading import read_tenuki
from kentogo.analysis.played_moves import played_move_loss, read_played_moves
from kentogo.analysis.query import QuerySettings

FIRST_STEP = "first"  # The analysis of the nodes without saved data.
REANALYSIS_STEP = "again"  # The analysis again (KaTrain's "Re-analyze game").
DEEP_STEP = "deep"  # The deep reading of the moves that can become problems.
END_OF_GAME = 100_000  # The end of the range of moves when move_to is 0.


@dataclass(frozen=True)
class DeepTargets:
    """Which moves are read deeply (see the module's docstring).

    Attributes:
        losses: The smallest loss of a move read deeply, by color ("B" and "W"); a color that is
            missing is not read deeply.
        visits: The visits of the deep reading.
        decided: Tells whether a position is decided, from black's winrate and score lead before the move
            (see mistakes.selection.Selection.is_decided); a move in a decided position is not read deeply.
    """

    losses: dict[str, float]
    visits: int
    decided: Callable[[float | None, float | None], bool] = field(default=lambda _winrate, _lead: False, compare=False)


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
    first = analysis_step(game, QuerySettings(visits, values.wide_root_noise, GAME_PRIORITY))
    analyze_with_retries(engine, game, first_nodes(game), first, _step(progress, FIRST_STEP), settings.retries)
    if settings.reanalyze:
        again_visits = settings.reanalyze_visits or reanalysis_visits(game, values.max_visits)
        again = analysis_step(game, QuerySettings(again_visits, values.wide_root_noise, REANALYSIS_PRIORITY))
        nodes = reanalysis_nodes(game, settings)
        analyze_with_retries(engine, game, nodes, again, _step(progress, REANALYSIS_STEP), settings.retries)
    read_played_moves(engine, game, values, progress, settings.retries)
    if targets is not None:
        read_deeply(engine, game, values, progress, settings.retries, targets)
    return game


def read_deeply(
    engine: Engine, game: GameAnalysis, values: EngineValues, progress: Progress, retries: int, targets: DeepTargets
) -> None:
    """Read the moves that can become problems deeply, and keep those that still lose enough as deep_nodes.

    The positions before and after each move are analyzed with the deep visits (unless they were read
    that deeply already), and the played move is read again in the position before it with those visits,
    so that the best move and the played move are compared at the same depth.
    """
    nodes = deep_candidates(game, targets)
    positions = []
    for node in nodes:
        for position in (node.parent, node):
            if position not in positions and _node_visits(game, position) < targets.visits:
                positions.append(position)
    deep = analysis_step(game, QuerySettings(targets.visits, values.wide_root_noise, REANALYSIS_PRIORITY))
    analyze_with_retries(engine, game, positions, deep, _step(progress, DEEP_STEP), retries)
    read_played_moves(engine, game, values, progress, retries, nodes)
    game.deep_nodes = deep_candidates(game, targets)
    game.deep_visits = targets.visits
    read_tenuki(engine, game, targets.visits, values.wide_root_noise, REANALYSIS_PRIORITY, progress, retries)


def deep_candidates(game: GameAnalysis, targets: DeepTargets) -> list[GoNode]:
    """Return the nodes whose move lost at least the smallest loss of its color, in a position that was not
    decided (see DeepTargets)."""
    found = []
    for node in game.nodes:
        move = node.move
        before = game.analysis(node.parent) if node.parent is not None else None
        if move is None or before is None:
            continue
        if targets.decided(before["root"].get("winrate"), before["root"].get("scoreLead")):
            continue
        loss = played_move_loss(game, node)
        if loss is not None and loss >= targets.losses.get(move.player, math.inf):
            found.append(node)
    return found


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
