"""Tests for kentogo.gui.board_geometry."""

import pytest

from kentogo.gui.board_geometry import BoardGeometry, star_points


def test_fit_in_a_wide_rectangle():
    """In a wide rectangle, the board is as tall as the rectangle and centered left to right.

    A 19x19 board needs 18 spacings, plus 1.5 and 0.75 for the margins: 20.25 spacings.
    """
    geometry = BoardGeometry.fit(19, 0, 0, 1010, 810)
    assert geometry.spacing == pytest.approx(40)
    assert geometry.to_screen((0, 0)) == pytest.approx((100 + 60, 60))
    assert geometry.to_screen((18, 18)) == pytest.approx((100 + 60 + 720, 60 + 720))


def test_fit_in_a_tall_rectangle():
    """In a tall rectangle, the board is as wide as the rectangle and centered top to bottom."""
    geometry = BoardGeometry.fit(9, 10, 20, 500, 900)
    assert geometry.spacing == pytest.approx(500 / 10.25)
    assert geometry.to_screen((0, 0)) == pytest.approx((10 + 1.5 * 500 / 10.25, 20 + 200 + 1.5 * 500 / 10.25))


def test_board_area_is_the_fitted_square():
    """The board image covers the square that the board was fitted into, with the margins."""
    geometry = BoardGeometry.fit(19, 0, 0, 1010, 810)
    assert geometry.board_area() == pytest.approx((100, 0, 810, 810))


def test_fit_with_padding():
    """Padding leaves the same space on every side of a square area."""
    geometry = BoardGeometry.fit(19, 0, 0, 850, 850, padding=20)
    assert geometry.board_area() == pytest.approx((20, 20, 810, 810))


def test_screen_and_point_go_both_ways():
    """Every point goes to the screen and back to the same point."""
    geometry = BoardGeometry.fit(19, 0, 0, 800, 800)
    for point in [(0, 0), (3, 15), (18, 18)]:
        assert geometry.to_point(*geometry.to_screen(point)) == point


def test_click_near_a_point():
    """A click less than half a spacing away from a point selects that point."""
    geometry = BoardGeometry.fit(19, 0, 0, 800, 800)
    x, y = geometry.to_screen((5, 5))
    assert geometry.to_point(x + geometry.spacing * 0.4, y - geometry.spacing * 0.4) == (5, 5)


def test_click_outside_the_board():
    """A click far from the board selects no point."""
    geometry = BoardGeometry.fit(19, 0, 0, 800, 800)
    x, y = geometry.to_screen((0, 0))
    assert geometry.to_point(x - geometry.spacing, y) is None
    assert geometry.to_point(*geometry.to_screen((19, 0))) is None


def test_stone_radius():
    """Stones are a little smaller than the spacing, so they do not touch."""
    geometry = BoardGeometry.fit(19, 0, 0, 800, 800)
    assert geometry.spacing / 2 * 0.9 < geometry.stone_radius < geometry.spacing / 2


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (19, {(3, 3), (3, 9), (3, 15), (9, 3), (9, 9), (9, 15), (15, 3), (15, 9), (15, 15)}),
        (13, {(3, 3), (3, 6), (3, 9), (6, 3), (6, 6), (6, 9), (9, 3), (9, 6), (9, 9)}),
        (9, {(2, 2), (2, 4), (2, 6), (4, 2), (4, 4), (4, 6), (6, 2), (6, 4), (6, 6)}),
        (7, {(2, 2), (2, 4), (4, 2), (4, 4)}),
        (5, set()),
    ],
)
def test_star_points(size, expected):
    """The star points are in the same places as in KaTrain."""
    assert set(star_points(size)) == expected
