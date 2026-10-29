"""Tests for kentogo.repetition.plan."""

from dataclasses import replace
from datetime import date, timedelta

from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import Problem
from kentogo.repetition.modes import PRIORITY_MIX, PRIORITY_NEW, PRIORITY_REVIEW
from kentogo.repetition.plan import plan_problems
from kentogo.repetition.schedule import DONE, STATE_REVIEW, ReviewState

TODAY = date(2026, 10, 21)

BASE = Problem(
    problem_id="",
    sgf_path="g.sgf",
    move_number=3,
    position=Position(19, 6.5, "japanese", (), (), "B"),
    actual_move=Move.from_gtp("A19", "B"),
    best_move=None,
    points_lost=8.0,
)


def problems(*ids: str) -> list[Problem]:
    """Make problems with the given IDs."""
    return [replace(BASE, problem_id=problem_id) for problem_id in ids]


def due(days_ago: int) -> ReviewState:
    """A review whose day was the given number of days ago (0: today, -1: tomorrow)."""
    return ReviewState(STATE_REVIEW, 0, TODAY - timedelta(days=days_ago))


STATES = {"done": DONE, "late": due(3), "today": due(0), "tomorrow": due(-1)}
ALL = problems("new1", "today", "done", "late", "tomorrow", "new2")


def ids(plan) -> list[str]:
    """Return the IDs of the planned problems."""
    return [problem.problem_id for problem in plan.problems]


def test_new_problems_first():
    """New problems come first, in their order, then the due reviews from the one that waited longest."""
    plan = plan_problems(ALL, STATES, TODAY, PRIORITY_NEW)
    assert ids(plan) == ["new1", "new2", "late", "today"]
    assert (plan.new_count, plan.review_count) == (2, 2)


def test_reviews_first():
    """With the other priority, the due reviews come first."""
    assert ids(plan_problems(ALL, STATES, TODAY, PRIORITY_REVIEW)) == ["late", "today", "new1", "new2"]


def test_same_position_is_asked_once():
    """A problem ID that is in two files is asked only once."""
    assert ids(plan_problems(problems("a", "a", "b"), {}, TODAY, PRIORITY_NEW)) == ["a", "b"]


def test_nothing_to_ask():
    """When all problems are done or not due, nothing is asked."""
    plan = plan_problems(problems("done", "tomorrow"), STATES, TODAY, PRIORITY_NEW)
    assert (plan.problems, plan.new_count, plan.review_count) == ([], 0, 0)


def test_mix():
    """In the mix order, two reviews come, then one new problem. When one group ends, the other goes on."""
    states = {f"r{i}": due(10 - i) for i in range(5)}
    all_problems = problems("n1", "n2", "n3", "n4", "r0", "r1", "r2", "r3", "r4")
    plan = plan_problems(all_problems, states, TODAY, PRIORITY_MIX)
    assert ids(plan) == ["r0", "r1", "n1", "r2", "r3", "n2", "r4", "n3", "n4"]


def test_excluded_problems_are_not_asked():
    """Problems set aside by the user are not asked, whatever their state."""
    plan = plan_problems(ALL, STATES, TODAY, PRIORITY_NEW, excluded={"new1", "late"})
    assert ids(plan) == ["new2", "today"]


def test_limit():
    """With a limit, only that many are asked, and the numbers count only those."""
    plan = plan_problems(ALL, STATES, TODAY, PRIORITY_REVIEW, limit=3)
    assert ids(plan) == ["late", "today", "new1"]
    assert (plan.new_count, plan.review_count) == (1, 2)
    assert plan_problems(ALL, STATES, TODAY, PRIORITY_REVIEW, limit=0).problems == []


def correct_last(days_ago: int) -> ReviewState:
    """A review answered correctly last time, whose day was the given number of days ago."""
    return ReviewState(STATE_REVIEW, 1, TODAY - timedelta(days=days_ago))


REVIEW_STATES = {"right_late": correct_last(5), "wrong_new": due(0), "wrong_late": due(2), "right_now": correct_last(0)}
REVIEWS = problems("n1", "right_late", "wrong_new", "wrong_late", "right_now", "n2")


def test_reviews_answered_wrong_come_first():
    """Among the reviews, those answered wrong last time come first, each group from the longest wait."""
    expected = ["wrong_late", "wrong_new", "right_late", "right_now"]
    assert ids(plan_problems(REVIEWS, REVIEW_STATES, TODAY, PRIORITY_REVIEW)) == [*expected, "n1", "n2"]


def test_with_new_problems_first_the_wrong_ones_start_the_reviews():
    """With new problems first, the new ones come, and then the reviews answered wrong last time."""
    expected = ["n1", "n2", "wrong_late", "wrong_new", "right_late", "right_now"]
    assert ids(plan_problems(REVIEWS, REVIEW_STATES, TODAY, PRIORITY_NEW)) == expected


def test_the_mix_starts_with_the_reviews_answered_wrong():
    """In the mix order, the reviews answered wrong last time are the first reviews."""
    expected = ["wrong_late", "wrong_new", "n1", "right_late", "right_now", "n2"]
    assert ids(plan_problems(REVIEWS, REVIEW_STATES, TODAY, PRIORITY_MIX)) == expected
