"""KataGo's candidate moves and policy ranking of a position, in the same way as KaTrain orders them.

Written for KentoGo with the same behavior as KaTrain 1.20.0's GameNode.candidate_moves and
policy_ranking (katrain/core/game_node.py), which are methods of KaTrain's GameNode class and cannot
be copied unchanged. KaTrain's own standalone helper var_to_grid is used unchanged
(vendor.katrain_analysis). The analyses are dicts with "root" (rootInfo of KataGo), "moves"
(moveInfos by GTP point) and "policy". KentoGo's comments (see analysis.kentogo_comment) and the marks of
the best moves (see analysis.sgf_writer) use them.
"""

from __future__ import annotations

from kentogo.common.types import Move
from kentogo.vendor.katrain_analysis import var_to_grid

_SIGNS = {"B": 1, "W": -1}  # KaTrain's GameNode.player_sign.


def top_candidate(analysis: dict, next_color: str, size: tuple[int, int]) -> dict:
    """Return KaTrain's top candidate move of a position (the first of GameNode.candidate_moves)."""
    return candidate_moves(analysis, next_color, size)[0]


def candidate_moves(analysis: dict, next_color: str, size: tuple[int, int]) -> list[dict]:
    """Return KaTrain's candidate moves of a position, as GameNode.candidate_moves.

    The candidates are sorted by KataGo's order and then by the points lost, and each gets its
    "pointsLost" (and KaTrain's "relativePointsLost" and "winrateLost"); without candidate moves,
    the move with the highest policy (or a pass) is the only candidate, as in KaTrain.
    """
    root = analysis["root"]
    moves = list((analysis.get("moves") or {}).values())
    if not moves:
        ranking = policy_ranking(analysis, next_color, size)
        point = ranking[0][1].gtp() if ranking else "pass"
        return [{**root, "pointsLost": 0, "winrateLost": 0, "order": 0, "move": point, "pv": [point]}]
    sign = _SIGNS[next_color]
    top = [values for values in moves if values["order"] == 0]
    top_score = top[0]["scoreLead"] if top else root["scoreLead"]
    candidates = [
        {
            "pointsLost": sign * (root["scoreLead"] - values["scoreLead"]),
            "relativePointsLost": sign * (top_score - values["scoreLead"]),
            "winrateLost": sign * (root["winrate"] - values["winrate"]),
            **values,
        }
        for values in moves
    ]
    return sorted(candidates, key=lambda values: (values["order"], values["pointsLost"]))


def policy_ranking(analysis: dict, next_color: str, size: tuple[int, int]) -> list[tuple[float, Move]]:
    """Return the moves from the highest policy value to the lowest, as KaTrain's GameNode.policy_ranking.

    The points are taken column by column from the left (each from the bottom), and the pass last;
    the sort keeps that order for equal values, as in KaTrain. Without a policy, the list is empty.
    """
    policy = analysis.get("policy")
    if not policy:
        return []
    columns, rows = size
    grid = var_to_grid(policy, size=(columns, rows))
    moves = [(grid[y][x], Move(next_color, (x, y))) for x in range(columns) for y in range(rows)]
    moves.append((policy[-1], Move(next_color, None)))
    return sorted(moves, key=lambda value_move: -value_move[0])
