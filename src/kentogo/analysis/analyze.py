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

A node that KataGo could not analyze is asked again (retries times). The answer for a position is
kept in that position only. KaTrain's own way (two separate analyses for a loss, the time limit,
the answer of a position changing the one before it) is not used: a game that needs it can be
analyzed with KaTrain itself.
"""

from __future__ import annotations

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
from kentogo.analysis.played_moves import played_move_loss, read_played_moves
from kentogo.analysis.query import QuerySettings

FIRST_STEP = "first"  # The analysis of the nodes without saved data.
REANALYSIS_STEP = "again"  # The analysis again (KaTrain's "Re-analyze game").
END_OF_GAME = 100_000  # The end of the range of moves when move_to is 0.


def analyze_game(
    engine: Engine, root: GoNode, settings: AnalysisSettings, values: EngineValues, progress: Progress
) -> GameAnalysis:
    """Analyze a game: the saved data, the first step, the analysis again when it is on, and the played moves.

    Args:
        engine: KataGo.
        root: The root node of the game.
        settings: The settings of the analysis.
        values: The engine settings that the analysis uses.
        progress: Called after each answer, in KataGo's thread, with the step, the answers and the queries.

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
    return game


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
