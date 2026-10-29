"""Tests for kentogo.gui.board_view."""

import pytest

from kentogo.common.types import Move, Position
from kentogo.gui.board_view import (
    MARK_ACTUAL,
    MARK_ANSWER,
    MARK_BEST,
    MARK_COMPARE,
    collect_marks,
    make_board_view,
    mark_outline,
)


def moves(text: str) -> tuple[Move, ...]:
    """Make moves from text such as "B:D4 W:D5"."""
    return tuple(Move.from_gtp(item[2:], item[0]) for item in text.split())


def point(gtp: str) -> tuple[int, int]:
    """Return the point of GTP coordinates."""
    return Move.from_gtp(gtp, "B").coord


def test_position_without_sequence():
    """The stones of the position are shown, and the last move is marked."""
    position = Position(9, 6.5, "japanese", (Move.from_gtp("C3", "B"),), moves("W:E5 B:D4"), "W")
    view = make_board_view(position)
    assert view.stones == {point("C3"): "B", point("E5"): "W", point("D4"): "B"}
    assert view.last_move == point("D4")
    assert view.numbers == {}


def test_sequence_gets_numbers():
    """The moves of a sequence are placed and numbered from 1."""
    position = Position(9, 6.5, "japanese", (), moves("B:E5"), "W")
    view = make_board_view(position, moves("W:D4 B:F4"))
    assert view.numbers == {point("D4"): 1, point("F4"): 2}
    assert view.stones[point("F4")] == "B"


def test_captured_numbered_stone_loses_its_number():
    """When a numbered stone is captured, its number is not shown."""
    position = Position(9, 6.5, "japanese", (), moves("W:E6 B:A1 W:E4 B:A2 W:D5"), "B")
    view = make_board_view(position, moves("B:E5 W:F5"))
    assert point("E5") not in view.stones
    assert view.numbers == {point("F5"): 2}


def test_illegal_move_stops_the_sequence():
    """A move that cannot be played, and the moves after it, are not shown."""
    position = Position(9, 6.5, "japanese", (), moves("B:E5"), "W")
    view = make_board_view(position, moves("W:D4 B:D4 W:F4"))
    assert view.numbers == {point("D4"): 1}
    assert point("F4") not in view.stones


def test_marks_are_kept():
    """The marks are passed to the view."""
    position = Position(9, 6.5, "japanese", (), (), "B")
    view = make_board_view(position, marks={point("E5"): (MARK_ANSWER,)})
    assert view.marks == {point("E5"): (MARK_ANSWER,)}
    assert view.last_move is None


def test_marks_on_the_same_point_are_kept_together():
    """Moves on the same point keep all their marks in order. Passes and unknown moves get none."""
    marks = collect_marks(
        [
            (Move.from_gtp("E5", "B"), MARK_ANSWER),
            (Move.from_gtp("C3", "B"), MARK_ACTUAL),
            (Move.from_gtp("E5", "B"), MARK_BEST),
            (Move.from_gtp("E5", "B"), MARK_COMPARE),
            (None, MARK_COMPARE),
            (Move("B", None), MARK_ACTUAL),
        ]
    )
    assert marks == {point("E5"): (MARK_ANSWER, MARK_BEST, MARK_COMPARE), point("C3"): (MARK_ACTUAL,)}


def test_mark_outlines():
    """Each kind has its own shape: a circle, a triangle, a square and a star."""
    assert mark_outline(MARK_ANSWER, (0, 0), 10) is None  # A circle.
    triangle = mark_outline(MARK_ACTUAL, (0, 0), 10)
    assert len(triangle) == 6 and triangle[:2] == pytest.approx([0, 10])  # Pointing up.
    square = mark_outline(MARK_BEST, (5, 5), 10)
    assert len(square) == 8 and all(abs(abs(value - 5) - 7.07) < 0.01 for value in square)
    star = mark_outline(MARK_COMPARE, (0, 0), 10)
    assert len(star) == 20 and star[2:4] != pytest.approx([0, 10])
