"""Count the territory of each player on a board, with the Japanese rules.

An empty area belongs to a player when all stones around it are that player's.
An area that touches stones of both players (dame) belongs to no one. Stones on
the board are not counted (the Japanese rules count only territory).

Dead stones are left out by the caller (see arrangement). Points marked as dame
(neutral points between the territories) are walls of no color: they are not
territory, they separate the areas, and they do not make an area touch a color.

Seki is found by seki.neutral_points. Its points are given here as neutral: they are
not territory, but they do not change the areas around them.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[int, int]


@dataclass(frozen=True)
class TerritoryCount:
    """The number of points of territory of each player.

    Attributes:
        black: Black's territory.
        white: White's territory.
    """

    black: int
    white: int


def count_territory(
    size: int,
    stones: dict[Point, str],
    dame: frozenset[Point] = frozenset(),
    neutral: frozenset[Point] = frozenset(),
) -> TerritoryCount:
    """Count the territory of each player.

    Args:
        size: The number of lines of the board.
        stones: The stones, as {point: "B" or "W"}.
        dame: Empty points marked as dame.
        neutral: Points that are never territory (the points of seki, see seki).

    Returns:
        The territory of each player.
    """
    owners = list(territory_owners(size, stones, dame, neutral).values())
    return TerritoryCount(owners.count("B"), owners.count("W"))


def territory_owners(
    size: int,
    stones: dict[Point, str],
    dame: frozenset[Point] = frozenset(),
    neutral: frozenset[Point] = frozenset(),
) -> dict[Point, str]:
    """Return the owner of each empty point that is territory, as {point: "B" or "W"}.

    Args:
        size: The number of lines of the board.
        stones: The stones, as {point: "B" or "W"}.
        dame: Empty points marked as dame (never territory, and walls between areas).
        neutral: Points that are never territory, but not walls (the points of seki, see seki).

    Returns:
        The territory points. Dame, neutral points and points with stones are not in it.
    """
    owners: dict[Point, str] = {}
    seen: set[Point] = set()
    for x in range(size):
        for y in range(size):
            if (x, y) in stones or (x, y) in seen or (x, y) in dame:
                continue
            area, borders = _empty_area((x, y), size, stones, dame)
            seen |= area
            if len(borders) == 1:
                color = next(iter(borders))
                owners.update(dict.fromkeys(area - neutral, color))
    return owners


def _empty_area(
    start: Point, size: int, stones: dict[Point, str], dame: frozenset[Point]
) -> tuple[set[Point], set[str]]:
    """Return the empty points connected to start (not across dame), and the colors of the stones around them."""
    area = {start}
    borders: set[str] = set()
    stack = [start]
    while stack:
        x, y = stack.pop()
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= neighbor[0] < size and 0 <= neighbor[1] < size) or neighbor in dame:
                continue
            if neighbor in stones:
                borders.add(stones[neighbor])
            elif neighbor not in area:
                area.add(neighbor)
                stack.append(neighbor)
    return area, borders


def majority_owners(size: int, stones: dict[Point, str], neutral: frozenset[Point] = frozenset()) -> dict[Point, str]:
    """Return the owner of each empty point, as a person counts after the seichi.

    After the seichi, the stones of a boundary are not always all of one color. An empty area
    belongs to the color of most of the stones around it (each stone once); when both colors
    have as many, it belongs to nobody. The points of seki are never territory.
    """
    owners: dict[Point, str] = {}
    seen: set[Point] = set(neutral)
    for x in range(size):
        for y in range(size):
            if (x, y) in stones or (x, y) in seen:
                continue
            area, around = _area_and_stones((x, y), size, stones, neutral)
            seen |= area
            colors = [stones[point] for point in around]
            black, white = colors.count("B"), colors.count("W")
            if black != white:
                owners.update(dict.fromkeys(area, "B" if black > white else "W"))
    return owners


def _area_and_stones(
    start: Point, size: int, stones: dict[Point, str], neutral: frozenset[Point]
) -> tuple[set[Point], set[Point]]:
    """Return the empty points connected to start (not across seki), and the stones next to them."""
    area, around, stack = {start}, set(), [start]
    while stack:
        x, y = stack.pop()
        for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= near[0] < size and 0 <= near[1] < size) or near in neutral:
                continue
            if near in stones:
                around.add(near)
            elif near not in area:
                area.add(near)
                stack.append(near)
    return area, around
