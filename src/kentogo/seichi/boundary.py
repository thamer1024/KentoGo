"""Make the boundary between the players clear at the end of the seichi, by swapping stones.

After the territory is packed (see block_tidy), a territory may touch the other player's stones,
and the stones between the territories may be mixed. People then swap black and white stones
so that each territory is closed by its own color's stones and the line between the colors is
short and straight. Swapping changes neither the territory nor the number of stones of a color.

The colors of the stones are chosen by a small integer program (scipy.optimize.milp):
- A stone next to the territory of only one player gets that player's color.
- A stone next to both players' territory, or next to seki, keeps its color.
- Each player keeps the number of stones on the board.
- The cost is the length of the line between the colors (EDGE_COST for stones side by side,
  CORNER_COST for stones corner to corner), and CHANGE_COST for each stone that changes color
  (so that few stones are swapped).
Then each black stone that turns white is swapped with a white stone that turns black, so that
the stones move as little as possible in total (see assignment).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from kentogo.seichi.assignment import cheapest_pairs

Point = tuple[int, int]

EDGE_COST = 1.0  # Two stones of different colors side by side.
CORNER_COST = 0.4  # Two stones of different colors corner to corner.
CHANGE_COST = 0.3  # A stone that changes color.
TIME_LIMIT = 3.0  # Seconds that the solver may take.


def clear_boundary(
    size: int, stones: dict[Point, str], owners: dict[Point, str], neutral: frozenset[Point] = frozenset()
) -> list[tuple[Point, Point]]:
    """Return the swaps that make the boundary between the players clear (see the module docstring).

    Args:
        size: The number of lines of the board.
        stones: The stones on the board. It is not changed.
        owners: The owner of each point of territory ("B" or "W").
        neutral: The points of seki.

    Returns:
        The swaps (a black stone, a white stone), the shortest first. Empty if nothing is better.
    """
    points = sorted(stones)
    fixed = {point: color for point in points if (color := _fixed_color(point, size, stones, owners, neutral))}
    colors = _solve(points, fixed, size, stones)
    if colors is None:
        return []
    to_white = [point for point in points if stones[point] == "B" and colors[point] == "W"]
    to_black = [point for point in points if stones[point] == "W" and colors[point] == "B"]
    if len(to_white) != len(to_black) or not to_white:
        return []
    cost = [[_distance(a, b) for b in to_black] for a in to_white]
    pairs = [(to_white[i], to_black[j]) for i, j in enumerate(cheapest_pairs(cost))]
    return sorted(pairs, key=lambda pair: (_distance(*pair), pair))


def _fixed_color(
    point: Point, size: int, stones: dict[Point, str], owners: dict[Point, str], neutral: frozenset[Point]
) -> str | None:
    """Return the color a stone must have: its territory's, or its own next to both territories or seki."""
    near = _neighbors(point, size)
    if any(p in neutral for p in near):
        return stones[point]
    sides = {owners[p] for p in near if p in owners and p not in stones}
    if len(sides) == 1:
        return sides.pop()
    return stones[point] if sides else None


def _solve(
    points: list[Point], fixed: dict[Point, str], size: int, stones: dict[Point, str]
) -> dict[Point, str] | None:
    """Choose the color of each stone with the integer program. None if there is no solution in time."""
    index = {point: number for number, point in enumerate(points)}
    edges = _edges(points, index, size)
    count = len(points) + len(edges)  # x (1: black) for each stone, then one cut for each edge.
    cost = np.zeros(count)
    rows: list[tuple[dict[int, float], float, float]] = []
    lower, upper = np.zeros(count), np.ones(count)
    for point, number in index.items():
        cost[number] = CHANGE_COST if stones[point] == "W" else -CHANGE_COST
        if point in fixed:
            lower[number] = upper[number] = 1.0 if fixed[point] == "B" else 0.0
    blacks = sum(1 for point in points if stones[point] == "B")
    rows.append((dict.fromkeys(range(len(points)), 1.0), blacks, blacks))
    for number, (a, b, weight) in enumerate(edges, start=len(points)):
        cost[number] = weight
        rows.append(({number: 1.0, a: -1.0, b: 1.0}, 0, np.inf))
        rows.append(({number: 1.0, a: 1.0, b: -1.0}, 0, np.inf))
    result = milp(
        c=cost,
        constraints=_constraint(rows, count),
        integrality=np.ones(count),
        bounds=Bounds(lower, upper),
        options={"time_limit": TIME_LIMIT},
    )
    if result.x is None:
        return None
    return {point: "B" if result.x[number] > 0.5 else "W" for point, number in index.items()}


def _edges(points: list[Point], index: dict[Point, int], size: int) -> list[tuple[int, int, float]]:
    """Return the pairs of stones side by side (EDGE_COST) and corner to corner (CORNER_COST), each once."""
    edges = []
    for x, y in points:
        for (dx, dy), weight in (
            ((1, 0), EDGE_COST),
            ((0, 1), EDGE_COST),
            ((1, 1), CORNER_COST),
            ((1, -1), CORNER_COST),
        ):
            near = (x + dx, y + dy)
            if near in index and 0 <= near[0] < size and 0 <= near[1] < size:
                edges.append((index[(x, y)], index[near], weight))
    return edges


def _constraint(rows: list[tuple[dict[int, float], float, float]], count: int) -> LinearConstraint:
    """Make the constraint of scipy from the rows (coefficients by variable, lowest, highest)."""
    data, row_index, column_index = [], [], []
    for number, (coefficients, _, _) in enumerate(rows):
        for column, value in coefficients.items():
            data.append(value)
            row_index.append(number)
            column_index.append(column)
    matrix = coo_matrix((data, (row_index, column_index)), shape=(len(rows), count)).tocsr()
    return LinearConstraint(matrix, [row[1] for row in rows], [row[2] for row in rows])


def _distance(a: Point, b: Point) -> int:
    """The number of steps between two points (along the lines)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors(point: Point, size: int) -> list[Point]:
    """Return the points next to a point (up, down, left, right) on the board."""
    x, y = point
    return [(a, b) for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if 0 <= a < size and 0 <= b < size]
