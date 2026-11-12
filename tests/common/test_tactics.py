"""Tests for kentogo.common.tactics (what a move does on the board)."""

from kentogo.common.board import Board
from kentogo.common.tactics import (
    ATARI,
    CAPTURE,
    CONNECT,
    DOUBLE_ATARI,
    EMPTY_TRIANGLE,
    ESCAPE,
    FAR,
    HANE,
    KO,
    KOSUMI,
    LADDER,
    PON_NUKI,
    SELF_ATARI,
    TSUKE,
    WEDGE,
    tactics,
)
from kentogo.common.types import Move, Position


def board(black: str = "", white: str = "") -> Board:
    """A 9x9 board with black and white stones (GTP points separated by spaces)."""
    stones = [Move.from_gtp(p, "B") for p in black.split()] + [Move.from_gtp(p, "W") for p in white.split()]
    return Board.from_position(Position(9, 6.5, "japanese", tuple(stones), (), "B"))


def black(point: str, on: Board, last: str | None = None) -> tuple[str, ...]:
    """What black's move at a point does."""
    return tactics(on, Move.from_gtp(point, "B"), Move.from_gtp(last, "W") if last else None)


def test_capture_and_ko():
    """Taking stones is a capture (a pon-nuki from all four sides); taking one stone into a ko is a ko capture."""
    assert PON_NUKI in black("E4", board("D5 F5 E6", "E5"))
    assert CAPTURE in black("A2", board("B1", "A1"))  # On the edge: not from four sides.
    ko = board("D5 E6 E4", "E5 F6 F4 G5")
    assert KO in black("F5", ko) and CAPTURE not in black("F5", ko)


def test_atari_and_double_atari():
    """One new atari, or two at once (here also a wedge between the two stones)."""
    single = black("F5", board("D5 E6", "E5"))
    assert ATARI in single and LADDER not in single  # The stone runs to E4 and gets three liberties.
    double = black("E5", board("C5 D6 G5 F6", "D5 F5"))
    assert DOUBLE_ATARI in double and WEDGE in double and ATARI not in double


def test_connect_and_escape():
    """Joining two groups is a connection; giving a group in atari more liberties is an escape."""
    assert CONNECT in black("E5", board("D5 F5"))
    assert ESCAPE in black("E4", board("E5", "D5 E6 F5"))


def test_ladder():
    """The stone runs toward the corner and is captured at the edge; a stone on the way saves it."""
    assert LADDER in black("F5", board("D5 E6 F4", "E5"))
    assert LADDER not in black("F5", board("D5 E6 F4", "E5 B2"))


def test_shapes_are_guesses():
    """A contact, a hane and a diagonal move are named by the stones next to them."""
    assert black("E6", board("", "E5")) == (TSUKE,)
    assert HANE in black("F5", board("E6", "E5"))
    assert black("E5", board("D4")) == (KOSUMI,)


def test_far_from_the_last_move():
    """A move with nothing else to tell, far from the opponent's last move."""
    assert black("B8", board("", "H2"), last="H2") == (FAR,)
    assert black("G3", board("", "H2"), last="H2") != (FAR,)


def test_a_pass_or_an_illegal_move_does_nothing():
    assert tactics(board(), Move("B", None), None) == ()
    assert black("E5", board("", "E5")) == ()


def test_empty_triangle_and_self_atari():
    """Three own stones and an empty point in a square; a move that leaves its own group one liberty."""
    assert EMPTY_TRIANGLE in black("E5", board("D5 D4"))
    assert SELF_ATARI in black("A1", board("", "A2 C1"))  # B1 is its only liberty.
