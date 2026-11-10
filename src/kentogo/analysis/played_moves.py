"""The value of each played move, read in the position before it.

KaTrain's loss of a move is the score before it minus the score after it: two separate analyses,
the second one from the opponent's side, so the noise of both goes into the loss. KentoGo
compares inside the position before the move instead: the best move's score with the played move's score.
When KataGo's analysis of that position already read the played move well enough (at least
PLAYED_SHARE of its visits), that value is used; otherwise the position is analyzed again with
only the played move allowed (KataGo's allowMoves), with the same visits as the position itself.
The value is kept in the candidates of the position before the move, so the analysis data (KT)
keeps KaTrain's format and KaTrain can still read it.

Saved analysis data counts only when KentoGo wrote it (the root's KGM[KentoGo]): in data that
KaTrain wrote, the played move's value comes from the position after it, so it is read again.
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
from kentogo.record.katrain_kt import KENTOGO_MODE
from kentogo.record.katrain_kt import played_move_loss as loss_in_position

PLAYED_SHARE = 0.1  # The played move is read well enough with this share of the position's visits.
PLAYED_STEP = "played"  # The name of this step in the progress.
MODE_MARK = KENTOGO_MODE  # The root's KGM property of games analyzed by KentoGo.


def played_move_loss(game: GameAnalysis, node: GoNode) -> float | None:
    """Return the points lost by a node's move from the best move, in the position before it.

    See record.katrain_kt.played_move_loss: the best move loses exactly 0, and a move better than
    KataGo's first choice gets a value below 0. When the played move was not read there (KataGo
    could not analyze it), the loss is the score before the move minus the score after it, as KaTrain.
    """
    move, parent = node.move, node.parent
    before = game.analysis(parent) if parent is not None else None
    loss = loss_in_position(before, move.player, move.gtp()) if before is not None and move is not None else None
    return game.points_lost(node) if loss is None else loss


def needs_reading(game: GameAnalysis, node: GoNode) -> bool:
    """True if the played move of a node was not read well enough in the position before it."""
    move, parent = node.move, node.parent
    before = game.analysis(parent) if parent is not None else None
    if move is None or before is None:
        return False
    if id(parent) in game.loaded and game.root.get_property("KGM", "") != MODE_MARK:
        return True  # Saved by KaTrain: the played move's value is not from this position.
    played = before["moves"].get(move.gtp())
    return played is None or played.get("visits", 0) < PLAYED_SHARE * before["root"].get("visits", 0)


def read_played_moves(
    engine: Engine,
    game: GameAnalysis,
    values: EngineValues,
    progress: Progress,
    retries: int,
    nodes: list[GoNode] | None = None,
) -> None:
    """Read played moves, each with the visits of the position before it, but at most values.max_visits.

    The first reading of the played moves (see analysis.analyze) is given the visits of the first analysis,
    so that a position that KaTrain read deeply does not make it slow; the deep reading gives its own visits.
    Each reading has the time limit of values (max_time).

    Args:
        nodes: The nodes whose moves are read, or None for those that need it (see needs_reading).
    """
    if nodes is None:
        nodes = [node for node in game.nodes if needs_reading(game, node)]

    def query(node: GoNode) -> dict | None:
        visits = max(game.visits.get(id(node.parent), 0), game.analysis(node.parent)["root"].get("visits", 0))
        visits = min(visits, values.max_visits) if visits else values.max_visits
        settings = QuerySettings(visits, values.wide_root_noise, GAME_PRIORITY, max_time=values.max_time)
        return played_move_query(node, settings)

    def keep(game: GameAnalysis, node: GoNode, answer: dict) -> None:
        apply_played_move(game.analyses[id(node.parent)], answer, node.move.gtp())

    step = NodeStep(query, keep)
    analyze_with_retries(engine, game, nodes, step, lambda done, total: progress(PLAYED_STEP, done, total), retries)
