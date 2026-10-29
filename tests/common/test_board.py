"""Tests for kentogo.common.board."""

import pytest

from kentogo.common.board import Board, IllegalMoveError
from kentogo.common.types import Move, Position


def play_all(board: Board, moves: str) -> None:
    """Play moves given as text such as "B:D4 W:D5 B:pass" on the board."""
    for item in moves.split():
        color, point = item.split(":")
        board.play(Move.from_gtp(point, color))


def stone(board: Board, gtp: str) -> str | None:
    """Return the stone at a point given in GTP coordinates."""
    return board.stone_at(Move.from_gtp(gtp, "B").coord)


def test_capture_one_stone():
    """A stone without liberties is removed and counted as a capture."""
    board = Board(9)
    play_all(board, "B:E5 W:E6 B:A1 W:E4 B:A2 W:D5")
    captured = board.play(Move.from_gtp("F5", "W"))
    assert captured == [Move.from_gtp("E5", "B").coord]
    assert stone(board, "E5") is None
    assert board.captures == {"B": 0, "W": 1}


def test_capture_group_on_the_edge():
    """A group of two stones on the edge is removed together."""
    board = Board(9)
    play_all(board, "B:A1 W:A2 B:B1 W:B2 B:J9")
    board.play(Move.from_gtp("C1", "W"))
    assert stone(board, "A1") is None and stone(board, "B1") is None
    assert board.captures["W"] == 2


def test_suicide_is_illegal():
    """A move that leaves its own group without liberties is not allowed, and the board does not change."""
    board = Board(9)
    play_all(board, "W:A2 W:B1")
    before = board.stones()
    with pytest.raises(IllegalMoveError):
        board.play(Move.from_gtp("A1", "B"))
    assert board.stones() == before


def test_capture_is_not_suicide():
    """Playing on the last liberty is allowed when it captures."""
    board = Board(9)
    play_all(board, "B:A2 W:A1 B:C1 W:B2")
    board.play(Move.from_gtp("B1", "B"))
    assert stone(board, "A1") is None
    assert stone(board, "B1") == "B"


def test_ko():
    """A single stone in a ko cannot be taken back at once, but can after another move."""
    board = Board(9)
    play_all(board, "B:D5 W:E5 B:C4 W:F4 B:D3 W:E3 B:E4 W:D4")
    assert stone(board, "E4") is None
    assert board.ko_point == Move.from_gtp("E4", "B").coord
    assert not board.is_legal(Move.from_gtp("E4", "B"))
    play_all(board, "B:J9 W:J8")
    assert board.ko_point is None
    board.play(Move.from_gtp("E4", "B"))
    assert stone(board, "D4") is None


def test_pass_clears_ko():
    """A pass also ends the ko restriction."""
    board = Board(9)
    play_all(board, "B:D5 W:E5 B:C4 W:F4 B:D3 W:E3 B:E4 W:D4 B:pass")
    assert board.ko_point is None


def test_capturing_two_stones_is_not_ko():
    """Taking two stones does not make a ko."""
    board = Board(9)
    play_all(board, "B:A2 B:B2 W:A3 W:B3 W:C2 W:B1")
    captured = board.play(Move.from_gtp("A1", "W"))
    assert len(captured) == 2
    assert board.ko_point is None


def test_occupied_and_outside_points():
    """A move on a stone or outside the board is not allowed."""
    board = Board(9)
    board.play(Move.from_gtp("E5", "B"))
    assert not board.is_legal(Move.from_gtp("E5", "W"))
    assert not board.is_legal(Move("B", (9, 0)))


def test_is_legal_does_not_change_the_board():
    """Checking a move does not place a stone."""
    board = Board(9)
    assert board.is_legal(Move.from_gtp("E5", "B"))
    assert board.stones() == {}


def test_from_position_with_handicap():
    """Setup stones are placed first, then the moves are played."""
    handicap = (Move.from_gtp("D4", "B"), Move.from_gtp("F6", "B"))
    position = Position(9, 0.5, "japanese", handicap, (Move.from_gtp("E5", "W"),), "B")
    board = Board.from_position(position)
    assert board.stones() == {
        (3, 3): "B",
        (5, 5): "B",
        (4, 4): "W",
    }


def test_copy_is_independent():
    """Changing a copy does not change the original board."""
    board = Board(9)
    copied = board.copy()
    copied.play(Move.from_gtp("E5", "B"))
    assert board.stones() == {}


def test_suicide_of_several_stones_when_allowed():
    """When the rules allow it, a suicide of two stones removes them, and the opponent gets them."""
    board = Board(9, allow_suicide=True)
    play_all(board, "W:A3 W:B2 W:B1 B:A1")
    removed = board.play(Move.from_gtp("A2", "B"))
    assert set(removed) == {(0, 0), (0, 1)}
    assert stone(board, "A1") is None and stone(board, "A2") is None
    assert board.captures == {"B": 0, "W": 2}


def test_suicide_of_several_stones_when_not_allowed():
    """Without that rule, the same move is not allowed."""
    board = Board(9)
    play_all(board, "W:A3 W:B2 W:B1 B:A1")
    assert not board.is_legal(Move.from_gtp("A2", "B"))


def test_single_stone_suicide_is_never_allowed():
    """A suicide of one stone is not allowed even when the rules allow suicide."""
    board = Board(9, allow_suicide=True)
    play_all(board, "W:A2 W:B1")
    assert not board.is_legal(Move.from_gtp("A1", "B"))


@pytest.mark.parametrize(("rules", "allowed"), [("japanese", False), ("chinese", False), ("tt", True), ("NZ", True)])
def test_from_position_uses_the_rules(rules, allowed):
    """The rules of the position decide whether suicide is allowed."""
    board = Board.from_position(Position(9, 7.5, rules, (), (), "B"))
    assert board.allow_suicide is allowed


def test_group_and_liberties():
    """A group is the connected stones of one color, and its liberties are the empty points next to it."""
    board = Board(9)
    play_all(board, "B:A1 W:E5 B:B1 W:A2")
    group = board.group_at(Move.from_gtp("A1", "B").coord)
    assert group == {(0, 0), (1, 0)}
    assert board.liberties(group) == {(2, 0), (1, 1)}
    assert board.group_at((4, 3)) == frozenset()  # An empty point.
