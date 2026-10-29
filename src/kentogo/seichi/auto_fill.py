"""Find how the computer would fill the territory with prisoners, so that it is easy to count.

The prisoners of a color go into the territory of that color (see arrangement).
The areas are filled so that the areas left are large and come in tens, which is
how territory is counted after seichi:

1. Small areas (less than ten points) are filled completely, the smallest first.
2. In the larger areas, as many prisoners as the points above a multiple of ten are
   put (for example one in an area of 21 points, which leaves 20).
3. Prisoners still left go in tens into the smallest large area, and the last few
   into the smallest area.

In an area, the stones go first where they fill a corner or a gap: on the points with
the fewest empty neighbors, so that the area left keeps a simple shape.

After that, the stones are moved block by block (see block_tidy).

This module only finds the points; Arrangement.auto_fill puts the stones there.
"""

from __future__ import annotations

from kentogo.seichi.territory import territory_owners

Point = tuple[int, int]
TEN = 10


def territory_areas(
    size: int, stones: dict[Point, str], dame: frozenset[Point], color: str, neutral: frozenset[Point] = frozenset()
) -> list[set[Point]]:
    """Return the areas (connected points) of the territory of a color (neutral points are not territory)."""
    owners = territory_owners(size, stones, dame, neutral)
    points = {point for point, owner in owners.items() if owner == color}
    areas = []
    while points:
        area = _connected(points.pop(), points)
        points -= area
        areas.append(area)
    return areas


def _connected(start: Point, points: set[Point]) -> set[Point]:
    """Return start and the points of a set that are connected to it."""
    area, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        new = [p for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if p in points and p not in area]
        area.update(new)
        stack.extend(new)
    return area


def fill_points(
    size: int,
    stones: dict[Point, str],
    dame: frozenset[Point],
    color: str,
    count: int,
    neutral: frozenset[Point] = frozenset(),
) -> list[Point]:
    """Return where to put a number of prisoners of a color in its territory (see the module).

    Args:
        size: The number of lines of the board.
        stones: The stones on the board (dead stones left out).
        dame: The points marked as dame.
        color: The color of the prisoners ("B" or "W").
        count: How many prisoners there are.
        neutral: Points that are never territory (the points of seki).

    Returns:
        The points, at most count of them (fewer when the territory is smaller).
    """
    areas = sorted(territory_areas(size, stones, dame, color, neutral), key=len)
    chosen: list[Point] = []
    left = count
    # 1. Small areas, completely, the smallest first.
    for area in [area for area in areas if len(area) < TEN]:
        take = min(left, len(area))
        chosen += nook_first(area, take, size, stones)
        left -= take
    # 2. The points above a multiple of ten in the larger areas, the smallest area first.
    for area in [area for area in areas if len(area) >= TEN]:
        extra = len(area) % TEN
        if 0 < extra <= left:
            chosen += nook_first(area, extra, size, {**stones, **dict.fromkeys(chosen, color)})
            left -= extra
    # 3. The rest: tens into the smallest large area, then the last few into the smallest area.
    while left > 0:
        taken = set(chosen)
        remaining = sorted((area - taken for area in areas if area - taken), key=len)
        if not remaining:
            break
        tens = [area for area in remaining if len(area) >= TEN]
        area = tens[0] if left >= TEN and tens else remaining[0]
        take = min(left, TEN if left >= TEN and tens else len(area))
        chosen += nook_first(area, take, size, {**stones, **dict.fromkeys(chosen, color)})
        left -= take
    return chosen


def nook_first(area: set[Point], count: int, size: int, stones: dict[Point, str]) -> list[Point]:
    """Choose points of an area one by one, each time the one with the fewest empty neighbors.

    Points at the edge of the board count the edge as filled. Ties go to the point nearest
    the edge of the board, then to the smallest point, so that the result is always the same.
    """
    free = set(area)
    filled = set(stones)
    chosen = []
    last = size - 1
    for _ in range(min(count, len(free))):

        def key(point: Point) -> tuple[int, int, Point]:
            """Empty neighbors, distance from the edge, and the point itself."""
            x, y = point
            empty = sum(
                1
                for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                if 0 <= neighbor[0] < size and 0 <= neighbor[1] < size and neighbor not in filled
            )
            return empty, min(x, y, last - x, last - y), point

        point = min(free, key=key)
        free.remove(point)
        filled.add(point)
        chosen.append(point)
    return chosen
