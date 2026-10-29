"""Tests for kentogo.quiz.order."""

import random
from dataclasses import replace

import pytest

from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import Problem
from kentogo.quiz.order import keep_newest, order_problems

TIMES = {"/games/a.sgf": 300.0, "/games/b.sgf": 100.0, "/games/c.sgf": 200.0}


def problem(path: str, loss: float) -> Problem:
    """Make a problem from a file, with a loss (only these values matter here)."""
    position = Position(19, 6.5, "japanese", (), (), "B")
    move = Move.from_gtp("A1", "B")
    return Problem(f"{path}{loss}", path, 1, position, move, None, loss)


# The problems as collect_problems returns them: games in any order, and the largest loss first in each game.
PROBLEMS = [
    problem("/games/c.sgf", 9.0),
    problem("/games/c.sgf", 4.0),
    problem("/games/a.sgf", 7.0),
    problem("/games/b.sgf", 5.0),
]


def files_and_losses(problems):
    """Return the file names and losses, to compare orders easily."""
    return [(p.sgf_path[-5:], p.points_lost) for p in problems]


def test_order_by_file_name():
    """Games are ordered by file name, and each game keeps its problems in order."""
    ordered = order_problems(PROBLEMS, "file_name", random.Random(0), TIMES.get)
    assert files_and_losses(ordered) == [("a.sgf", 7.0), ("b.sgf", 5.0), ("c.sgf", 9.0), ("c.sgf", 4.0)]


def test_order_newest_first():
    """Games are ordered from the file changed last, and each game keeps its problems in order."""
    ordered = order_problems(PROBLEMS, "newest", random.Random(0), TIMES.get)
    assert files_and_losses(ordered) == [("a.sgf", 7.0), ("c.sgf", 9.0), ("c.sgf", 4.0), ("b.sgf", 5.0)]


def test_random_order():
    """All problems are mixed, the same seed gives the same order, and the list given is not changed."""
    before = list(PROBLEMS)
    first = order_problems(PROBLEMS, "random", random.Random(3), TIMES.get)
    assert first == order_problems(PROBLEMS, "random", random.Random(3), TIMES.get)
    assert sorted(first, key=id) == sorted(PROBLEMS, key=id)
    assert PROBLEMS == before
    orders = {tuple(map(id, order_problems(PROBLEMS, "random", random.Random(seed), TIMES.get))) for seed in range(20)}
    assert len(orders) > 1


def test_unknown_order():
    """An unknown order is an error."""
    with pytest.raises(ValueError):
        order_problems(PROBLEMS, "oldest", random.Random(0), TIMES.get)


def test_keep_newest():
    """The same position in two files is kept only from the newer file, and the order stays."""
    same_in_b = replace(problem("/games/b.sgf", 5.0), problem_id="same")
    same_in_a = replace(problem("/games/a.sgf", 7.0), problem_id="same")
    other = problem("/games/c.sgf", 9.0)
    kept = keep_newest([same_in_b, other, same_in_a], TIMES.__getitem__)
    assert kept == [other, same_in_a]  # a.sgf (300) is newer than b.sgf (100).


def test_keep_newest_with_a_missing_file():
    """A file that cannot be read counts as the oldest."""

    def modified_time(path):
        if path == "/games/a.sgf":
            raise FileNotFoundError(path)
        return TIMES[path]

    same_in_a = replace(problem("/games/a.sgf", 7.0), problem_id="same")
    same_in_b = replace(problem("/games/b.sgf", 5.0), problem_id="same")
    assert keep_newest([same_in_a, same_in_b], modified_time) == [same_in_b]
