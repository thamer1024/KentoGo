"""Tests for kentogo.mistakes.problem."""

from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import problem_id_of

Q16 = Move.from_gtp("Q16", "B")
D4 = Move.from_gtp("D4", "W")


def position(moves=(Q16, D4), setup=(), size=19, komi=6.5, rules="japanese") -> Position:
    """Make a position for the tests."""
    return Position(size, komi, rules, setup, moves, "B")


def test_same_position_same_id():
    """The same position always gets the same ID, with 16 hexadecimal letters."""
    problem_id = problem_id_of(position())
    assert problem_id == problem_id_of(position())
    assert len(problem_id) == 16
    assert all(letter in "0123456789abcdef" for letter in problem_id)


def test_id_does_not_depend_on_komi_or_rules():
    """Komi and rules do not change the position, so they do not change the ID."""
    assert problem_id_of(position(komi=0.5, rules="chinese")) == problem_id_of(position())


def test_id_does_not_depend_on_the_order_of_setup_stones():
    """Setup stones are placed at the same time, so their order does not matter."""
    stones = (Move.from_gtp("D4", "B"), Move.from_gtp("Q16", "B"))
    assert problem_id_of(position(moves=(), setup=stones)) == problem_id_of(position(moves=(), setup=stones[::-1]))


def test_different_positions_different_ids():
    """The order of moves, setup stones, and board size all change the ID."""
    ids = {
        problem_id_of(position()),
        problem_id_of(position(moves=(Move.from_gtp("D4", "B"), Move.from_gtp("Q16", "W")))),
        problem_id_of(position(moves=(Q16,))),
        problem_id_of(position(moves=(Q16,), setup=(Move.from_gtp("D4", "W"),))),
        problem_id_of(position(size=13)),
    }
    assert len(ids) == 5
