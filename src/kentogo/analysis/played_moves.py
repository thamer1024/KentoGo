"""KentoGo's mode: the value of each played move, read in the position before it.

KaTrain's loss of a move is the score before it minus the score after it: two separate analyses,
the second one from the opponent's side, so the noise of both goes into the loss. KentoGo's mode
compares inside the position before the move instead: its own score with the played move's score.
When KataGo's analysis of that position already read the played move well enough (at least
PLAYED_SHARE of its visits), that value is used; otherwise the position is analyzed again with
only the played move allowed (KataGo's allowMoves), with the same visits as the position itself.
The value is kept in the candidates of the position before the move, so the analysis data (KT)
keeps KaTrain's format and KaTrain can still read it.

Saved analysis data counts only when KentoGo's mode wrote it (the root's KGM[KentoGo]): in data that
KaTrain (or the compatible mode) wrote, the played move's value comes from the position after it.
"""

from __future__ import annotations

from pysgf import GoNode

from kentogo.analysis.game_analysis import (
    GAME_PRIORITY,
    Engine,
    EngineValues,
    GameAnalysis,
    NodeStep,
    Progress,
    analyze_with_retries,
)
from kentogo.analysis.node_analysis import apply_played_move
from kentogo.analysis.query import QuerySettings, played_move_query

PLAYED_SHARE = 0.1  # The played move is read well enough with this share of the position's visits.
PLAYED_STEP = "played"  # The name of this step in the progress.
MODE_MARK = "KentoGo"  # The root's KGM property of games analyzed in KentoGo's mode.
_SIGNS = {"B": 1, "W": -1}


def played_move_loss(game: GameAnalysis, node: GoNode) -> float | None:
    """Return the points lost by a node's move, read in the position before it (or as KaTrain when not there)."""
    move, parent = node.move, node.parent
    before = game.analysis(parent) if parent is not None else None
    played = (before or {}).get("moves", {}).get(move.gtp()) if move is not None else None
    if before is None or played is None or "scoreLead" not in played:
        return game.points_lost(node)
    return _SIGNS[move.player] * (before["root"]["scoreLead"] - played["scoreLead"])


def needs_reading(game: GameAnalysis, node: GoNode) -> bool:
    """True if the played move of a node was not read well enough in the position before it."""
    move, parent = node.move, node.parent
    before = game.analysis(parent) if parent is not None else None
    if move is None or before is None:
        return False
    if id(parent) in game.loaded and game.root.get_property("KGM", "") != MODE_MARK:
        return True  # Saved by KaTrain's way: the played move's value is not from this position.
    played = before["moves"].get(move.gtp())
    return played is None or played.get("visits", 0) < PLAYED_SHARE * before["root"].get("visits", 0)


def read_played_moves(
    engine: Engine, game: GameAnalysis, values: EngineValues, progress: Progress, retries: int
) -> None:
    """Read the played moves that need it, each with the visits of the position before it."""
    nodes = [node for node in game.nodes if needs_reading(game, node)]

    def query(node: GoNode) -> dict | None:
        visits = max(game.visits.get(id(node.parent), 0), game.analysis(node.parent)["root"].get("visits", 0))
        settings = QuerySettings(visits or values.max_visits, values.wide_root_noise, None, GAME_PRIORITY)
        return played_move_query(node, settings)

    def keep(game: GameAnalysis, node: GoNode, answer: dict) -> None:
        apply_played_move(game.analyses[id(node.parent)], answer, node.move.gtp())

    step = NodeStep(query, keep)
    analyze_with_retries(engine, game, nodes, step, lambda done, total: progress(PLAYED_STEP, done, total), retries)
