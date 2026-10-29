"""Tests for kentogo.seichi.auto_fill."""

from kentogo.seichi.auto_fill import fill_points, territory_areas


def black_areas(sizes: list[int], size: int = 19) -> dict:
    """Make black territory areas of the given sizes, each in its own row, closed by black stones.

    Row y has the area at x = 0 .. n-1, and black stones above it (row y+1), at x = n,
    and below it (row y-1) for the rows that need them. Rows are three apart.
    """
    stones = {}
    for index, length in enumerate(sizes):
        y = 1 + index * 3
        for x in range(length + 1):
            stones[(x, y - 1)] = "B"
            stones[(x, y + 1)] = "B"
        stones[(length, y)] = "B"
    return stones


def test_areas_of_a_color():
    """The areas of a color's territory are found with their sizes."""
    stones = black_areas([3, 12])
    assert sorted(len(area) for area in territory_areas(19, stones, frozenset(), "B"))[:2] == [3, 12]


def test_small_areas_first_then_the_points_above_ten():
    """With 5 prisoners: the area of 3 is filled, then 2 go into the area of 12 (which becomes 10)."""
    stones = black_areas([3, 12])
    points = fill_points(19, stones, frozenset(), "B", 5)
    filled = {**stones, **dict.fromkeys(points, "B")}
    sizes = sorted(len(area) for area in territory_areas(19, filled, frozenset(), "B"))
    assert len(points) == 5 and 3 not in sizes and 10 in sizes and 12 not in sizes


def test_more_prisoners_than_territory():
    """When the territory is too small, every point is filled and the rest is left over."""
    stones = black_areas([2])
    areas = territory_areas(19, stones, frozenset(), "B")
    total = sum(len(area) for area in areas)
    assert len(fill_points(19, stones, frozenset(), "B", total + 5)) == total


def test_no_prisoners():
    """Without prisoners, nothing is put."""
    assert fill_points(19, black_areas([3]), frozenset(), "B", 0) == []
