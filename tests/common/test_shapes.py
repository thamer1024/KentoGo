"""Tests for kentogo.common.shapes (the names of the shape of a move, and the cutting points).

The cases of the user's own prototype (kento_prompt, tests/test_shapes.py), on KentoGo's board.
"""

from kentogo.common.board import Board
from kentogo.common.shapes import (
    CONNECT,
    CUT,
    HANE,
    IKKEN,
    KEIMA,
    KOSUMI,
    NOBI,
    SAGARI,
    TSUKE,
    WEDGE,
    Shape,
    cut_points,
    shapes_of,
)
from kentogo.common.types import Move, Position


def board(black: str = "", white: str = "") -> Board:
    """A 19x19 board with black and white stones (GTP points separated by spaces)."""
    stones = [Move.from_gtp(p, "B") for p in black.split()] + [Move.from_gtp(p, "W") for p in white.split()]
    return Board.from_position(Position(19, 6.5, "japanese", tuple(stones), (), "B"))


def points(text: str) -> tuple:
    """The points of GTP names."""
    return tuple(Move.from_gtp(p, "B").coord for p in text.split())


def shapes(on: Board, color: str, gtp: str) -> tuple[Shape, ...]:
    return shapes_of(on, Move.from_gtp(gtp, color))


def test_wedge():
    assert Shape(WEDGE, points("N3 P3")) in shapes(board("N3 P3", "P4"), "W", "O3")


def test_a_cut_leaves_out_the_tsuke():
    found = shapes(board("N3 P3", "P4 O3"), "B", "O4")
    assert Shape(CUT, points("P4 O3")) in found and TSUKE not in [shape.name for shape in found]


def test_a_hane_keeps_all_its_stones():
    assert shapes(board("N3 P3", "O3"), "B", "O2") == (Shape(HANE, points("P3 N3")),)


def test_connect():
    assert shapes(board("", "O3 P4"), "W", "O4") == (Shape(CONNECT, points("P4 O3")),)


def test_only_one_shape_at_a_distance():
    """A kosumi and a keima at once: only the kosumi."""
    assert shapes(board("P18 Q17"), "B", "O17") == (Shape(KOSUMI, points("P18")),)


def test_sagari_nobi_tsuke_ikken_keima():
    assert shapes(board("O3", "P3"), "B", "O2") == (Shape(SAGARI, points("O3")),)
    assert shapes(board("O5", "P6"), "B", "O6") == (Shape(NOBI, points("O5")),)
    assert shapes(board("", "K10"), "B", "K11") == (Shape(TSUKE, points("K10")),)
    assert shapes(board("K10"), "B", "K12") == (Shape(IKKEN, points("K10")),)
    assert shapes(board("K10"), "B", "L12") == (Shape(KEIMA, points("K10")),)


def test_cut_points():
    assert cut_points(board("N3 O2 P3", "O3"), "B") == sorted(points("N2 P2"))


def test_no_shape_for_a_pass_or_an_occupied_point():
    assert shapes_of(board("K10"), Move("B", None)) == ()
    assert shapes(board("K10"), "B", "K10") == ()
