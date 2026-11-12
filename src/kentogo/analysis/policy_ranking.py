"""KataGo's policy ranking of a position (its first instinct), in the same way as KaTrain orders it.

Written for KentoGo with the same behavior as KaTrain 1.20.0's GameNode.policy_ranking
(katrain/core/game_node.py), which is a method of KaTrain's GameNode class and cannot be copied
unchanged. KaTrain's own standalone helper var_to_grid is used unchanged (vendor.katrain_analysis).
The first instinct of a move that can become a problem is kept with its analysis (see analysis.sgf_writer).
"""

from __future__ import annotations

from kentogo.common.types import Move
from kentogo.vendor.katrain_analysis import var_to_grid


def policy_ranking(analysis: dict, next_color: str, size: tuple[int, int]) -> list[tuple[float, Move]]:
    """Return the moves from the highest policy value to the lowest, as KaTrain's GameNode.policy_ranking.

    The analysis has "policy": KataGo's policy (row by row from the top, the pass last). The points are
    taken column by column from the left (each from the bottom), and the pass last; the sort keeps that
    order for equal values, as in KaTrain. Without a policy, the list is empty.
    """
    policy = analysis.get("policy")
    if not policy:
        return []
    columns, rows = size
    grid = var_to_grid(policy, size=(columns, rows))
    moves = [(grid[y][x], Move(next_color, (x, y))) for x in range(columns) for y in range(rows)]
    moves.append((policy[-1], Move(next_color, None)))
    return sorted(moves, key=lambda value_move: -value_move[0])
