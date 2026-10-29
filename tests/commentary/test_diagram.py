"""Tests for kentogo.commentary.diagram."""

from kentogo.commentary.diagram import MARK_BEST, MARK_PLAYED, Region, region_around, render
from kentogo.common.types import Move


def test_render_whole_board():
    """Stones, the last move and the marks are drawn, with the top row first."""
    stones = {(0, 0): "B", (1, 0): "W", (2, 2): "W"}
    text = render(stones, Region.whole(3), Move("W", (2, 2)), {(1, 1): MARK_PLAYED, (0, 2): MARK_BEST})
    assert text.splitlines() == [
        "   A B C",
        " 3 * . o 3",
        " 2 . # . 2",
        " 1 X O . 1",
        "   A B C",
    ]


def test_region_around():
    """The region has the points with a margin, is at least the minimum size, and stays on the board."""
    assert region_around([(9, 9)], 19, 3, 9) == Region(5, 5, 13, 13)
    assert region_around([(0, 0)], 19, 3, 9) == Region(0, 0, 8, 8)
    assert region_around([(18, 18), (10, 18)], 19, 3, 9) == Region(7, 10, 18, 18)
    assert region_around([(18, 9)], 19, 1, 9) == Region(10, 5, 18, 13)
    assert region_around([(1, 1)], 5, 3, 9) == Region(0, 0, 4, 4)
    assert region_around([], 9, 3, 9) == Region.whole(9)
