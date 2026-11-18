"""Tests for kentogo.repetition.counts."""

from datetime import date

from kentogo.repetition.counts import ProblemCounts, count_problems
from kentogo.repetition.schedule import DONE, STATE_REVIEW, ReviewState


def test_problems_are_counted_by_their_state():
    """A problem without a state is new, and only the problems asked for are counted."""
    states = {"done": DONE, "review": ReviewState(STATE_REVIEW, 1, date(2026, 11, 20)), "other": DONE}
    counts = count_problems(["done", "review", "new", "new"], states)
    assert counts == ProblemCounts(1, 1, 1)
    assert counts.total == 3
