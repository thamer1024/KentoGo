"""The query that KaTrain sends to KataGo to analyze one node of a game.

Written for KentoGo with the same contents as KaTrain 1.20.0's KataGoEngine.request_analysis
(katrain/core/engine.py), which is a method of KaTrain's engine class and cannot be copied
unchanged: the moves and the placed stones from the start of the game to the node, the rules,
komi and board size, the visits, the ownership and the policy, and KaTrain's settings
(scores from black's side and wide root noise). KentoGo sets no time limit, so every position is
read with all its visits.
KaTrain's own key for continuous analysis ("_kt_continuous") is not sent to KataGo, so it is not here.
"""

from __future__ import annotations

from dataclasses import dataclass

from pysgf import GoNode

from kentogo.common.rules import normalize_rules

FORCED_SETTINGS = {"reportAnalysisWinratesAs": "BLACK"}  # KaTrain's KataGoEngine.override_settings.


@dataclass(frozen=True)
class QuerySettings:
    """How a node is analyzed.

    Attributes:
        visits: KataGo's maxVisits.
        wide_root_noise: KaTrain's engine setting "wide_root_noise".
        priority: KataGo's priority of the query (KaTrain: -100 for a game, -1000000 for re-analysis).
        ownership: Ask for the ownership (KaTrain's engine setting "_enable_ownership", on by default).
    """

    visits: int
    wide_root_noise: float
    priority: int
    ownership: bool = True


def played_move_query(node: GoNode, settings: QuerySettings) -> dict | None:
    """Return the query that analyzes the position before a node with only the node's move allowed.

    It is the query of the node before (see node_query), with KataGo's allowMoves for the first move,
    and without the ownership and the policy, which the answer does not need.
    """
    query = node_query(node.parent, settings)
    if query is None:
        return None
    move = node.move
    allowed = [{"player": move.player, "moves": [move.gtp()], "untilDepth": 1}]
    return {
        **query,
        "allowMoves": allowed,
        "includeOwnership": False,
        "includeMovesOwnership": False,
        "includePolicy": False,
    }


def node_query(node: GoNode, settings: QuerySettings) -> dict | None:
    """Return KaTrain's query for a node, or None when KaTrain does not analyze it.

    KaTrain does not analyze a node when stones are removed (AE) on the way to it.
    """
    nodes = node.nodes_from_root
    if any(item.clear_placements for item in nodes):
        return None
    moves = [move for item in nodes for move in item.moves]
    stones = [move for item in nodes for move in item.placements]
    override = {**FORCED_SETTINGS, "wideRootNoise": settings.wide_root_noise}
    size_x, size_y = node.board_size
    return {
        "rules": normalize_rules(node.ruleset),
        "priority": settings.priority,
        "analyzeTurns": [len(moves)],
        "maxVisits": settings.visits,
        "komi": node.komi,
        "boardXSize": size_x,
        "boardYSize": size_y,
        "includeOwnership": settings.ownership,
        "includeMovesOwnership": settings.ownership,
        "includePolicy": True,
        "initialStones": [[stone.player, stone.gtp()] for stone in stones],
        "initialPlayer": node.initial_player,
        "moves": [[move.player, move.gtp()] for move in moves],
        "overrideSettings": override,
    }
