"""Tests for kentogo.common.places (the region and the line of a point)."""

from kentogo.common.places import CENTER, line_of, region_of
from kentogo.common.types import Move


def point(gtp: str) -> tuple[int, int]:
    return Move.from_gtp(gtp, "B").coord


def test_regions():
    """The same regions as the user's own prototype."""
    assert region_of(point("Q16"), 19) == "top_right_corner"
    assert region_of(point("O17"), 19) == "top_right"
    assert region_of(point("R11"), 19) == "right_side"
    assert region_of(point("K3"), 19) == "bottom_side"
    assert region_of(point("K10"), 19) == CENTER
    assert region_of(point("C3"), 19) == "bottom_left_corner"


def test_lines():
    assert [line_of(point(gtp), 19) for gtp in ("A1", "C3", "R11", "K10")] == [1, 3, 3, 10]
