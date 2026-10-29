"""Find the points that are not territory because of seki, with goscorer.

Counting only which color surrounds an empty area (see territory) would count the
eyes of groups in seki as territory. The Japanese rules do not: there is no territory
in seki. goscorer (by lightvector, see THIRD_PARTY_NOTICES.md) looks at the life of
the groups and tells which points really are territory, given the dead stones. It also
leaves out false eyes that must be filled in the end.

It is used on the final position of the game, with the stones the user marked dead (or
took off as dead): the points it does not count are "neutral" during the whole seichi,
like dame. It is not used on the stones while they are arranged, because there the groups
do not need two eyes (as in seichi), and goscorer would see seki everywhere.
"""

from __future__ import annotations

from functools import lru_cache

from kentogo.seichi.territory import territory_owners
from kentogo.vendor import goscorer

Point = tuple[int, int]

_COLORS = {"B": goscorer.BLACK, "W": goscorer.WHITE}


def neutral_points(size: int, stones: dict[Point, str], dead: frozenset[Point]) -> frozenset[Point]:
    """Return the points that are nobody's territory because of seki (or false eyes).

    Args:
        size: The number of lines of the board.
        stones: The stones of the final position.
        dead: The stones marked dead (or taken off as dead).

    Returns:
        The points that look like territory (only the surrounding color is looked at) but that
        goscorer does not count, and the empty points next to a group in seki (its eyes and the
        liberties it shares, which cannot be filled without putting a group in atari).
    """
    return _neutral(size, tuple(sorted(stones.items())), frozenset(dead & stones.keys()))


@lru_cache(maxsize=64)
def _neutral(size: int, stones: tuple[tuple[Point, str], ...], dead: frozenset[Point]) -> frozenset[Point]:
    """neutral_points with arguments that can be kept in the cache."""
    board = dict(stones)
    grid = [[_COLORS.get(board.get((x, y)), goscorer.EMPTY) for x in range(size)] for y in range(size)]
    marked = [[(x, y) in dead for x in range(size)] for y in range(size)]
    scores = goscorer.territory_scoring(grid, marked)
    live = {point: color for point, color in board.items() if point not in dead}
    simple = territory_owners(size, live)
    neutral = {point for point in simple if scores[point[1]][point[0]].is_territory_for != _COLORS[simple[point]]}
    for x in range(size):
        for y in range(size):
            if (x, y) in live or scores[y][x].is_territory_for != goscorer.EMPTY:
                continue
            near = ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            if any(p in live and scores[p[1]][p[0]].belongs_to_seki_group != goscorer.EMPTY for p in near):
                neutral.add((x, y))
    return frozenset(neutral)
