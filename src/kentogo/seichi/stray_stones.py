"""Find stones that stand in the other player's territory after the seichi (相手の地に紛れ込んだ石).

After a seichi, every stone must belong to the walls of its own color or fill its own
color's territory: a black stone may not be left inside white's territory, and the other
way round. Such a stone is found as a group of stones of one color whose empty neighbors
are all territory of the other color (with no point of seki or of nobody next to it).
"""

from __future__ import annotations

Point = tuple[int, int]


def stray_stones(size: int, stones: dict[Point, str], owners: dict[Point, str]) -> set[Point]:
    """Return the stones that stand in the other player's territory.

    Args:
        size: The number of lines of the board.
        stones: The stones, as {point: "B" or "W"}.
        owners: The owner of each empty point of territory ("B" or "W"); other empty points are nobody's.

    Returns:
        The points of the stones of every group whose empty neighbors are all the other color's territory.
    """
    stray: set[Point] = set()
    seen: set[Point] = set()
    for point in sorted(stones):
        if point in seen:
            continue
        group, empty = _group_and_empty_neighbors(point, size, stones)
        seen |= group
        color = stones[point]
        if empty and all(owners.get(near) not in (None, color) for near in empty):
            stray |= group
    return stray


def _group_and_empty_neighbors(start: Point, size: int, stones: dict[Point, str]) -> tuple[set[Point], set[Point]]:
    """Return the stones of the same color connected to start, and the empty points next to them."""
    color = stones[start]
    group, empty, stack = {start}, set(), [start]
    while stack:
        x, y = stack.pop()
        for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= near[0] < size and 0 <= near[1] < size):
                continue
            if near not in stones:
                empty.add(near)
            elif stones[near] == color and near not in group:
                group.add(near)
                stack.append(near)
    return group, empty
