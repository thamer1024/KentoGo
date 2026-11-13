"""Tests for kentogo.quiz.judge."""

import pytest

from kentogo.quiz.judge import ScoringPolicy, judge_answer
from kentogo.quiz.score import compare_with_actual

POLICY = ScoringPolicy(small_problem_threshold=3.0, pass_ratio=0.8, tolerance=1.0)


@pytest.mark.parametrize(
    ("actual_loss", "answer_loss", "correct"),
    [
        (2.0, 2.0, True),  # Not worse than the game move.
        (2.0, 1.5, True),
        (2.0, 2.5, False),  # Worse than the game move, and more than the tolerance.
        (0.6, 0.9, True),  # Worse than the game move, but within the tolerance.
    ],
)
def test_small_problems(actual_loss, answer_loss, correct):
    """A small problem is correct if the answer is not worse than the game move, or within the tolerance."""
    assert judge_answer(actual_loss, answer_loss, POLICY) is correct


@pytest.mark.parametrize(
    ("actual_loss", "answer_loss", "correct"),
    [
        (10.0, 2.0, True),  # Gets back 80%.
        (10.0, 2.1, False),  # Gets back 79%.
        (3.0, 1.0, True),  # Gets back only 67%, but within the tolerance.
        (3.0, 1.1, False),  # The threshold itself is not a small problem.
    ],
)
def test_normal_problems(actual_loss, answer_loss, correct):
    """A normal problem is correct if the answer gets back enough, or is within the tolerance."""
    assert judge_answer(actual_loss, answer_loss, POLICY) is correct


LIMITED = ScoringPolicy(small_problem_threshold=3.0, pass_ratio=0.7, tolerance=1.0, max_answer_loss=5.0)


@pytest.mark.parametrize(
    ("actual_loss", "answer_loss", "correct"),
    [
        (20.0, 5.0, True),  # Gets back 75%, and loses no more than the limit.
        (20.0, 5.5, False),  # Gets back 72.5%, but loses more than the limit of 5 points.
        (10.0, 3.0, True),  # Gets back 70%: the limit does not matter here.
        (10.0, 3.1, False),  # Gets back 69%.
        (2.0, 2.0, True),  # A small problem: the limit is not used.
    ],
)
def test_limit_of_the_answer_loss(actual_loss, answer_loss, correct):
    """With a limit, an answer to a big problem must also lose at most that many points."""
    assert judge_answer(actual_loss, answer_loss, LIMITED) is correct


def test_the_default_rule_is_for_beginners():
    """By default, 60% of the loss is enough, with no limit: 20 points lost in the game, 8 lost by the answer."""
    assert ScoringPolicy().pass_ratio == 0.6 and ScoringPolicy().max_answer_loss == 0.0
    assert judge_answer(20.0, 8.0, ScoringPolicy()) is True
    assert judge_answer(20.0, 8.2, ScoringPolicy()) is False


@pytest.mark.parametrize(
    ("actual_loss", "answer_loss", "correct"),
    [
        (24.0, 5.04, True),  # Shown as 5.0 points: within the limit of 5.0 (it got back 79%).
        (24.0, 5.06, False),  # Shown as 5.1 points.
        (10.0, 3.04, True),  # Shown as 3.0 points: it got back 70%.
    ],
)
def test_the_losses_are_judged_as_they_are_shown(actual_loss, answer_loss, correct):
    """The losses are rounded to 0.1 points before they are judged, as the screen shows them."""
    assert judge_answer(actual_loss, answer_loss, LIMITED) is correct


def test_the_part_got_back_is_judged_as_it_is_shown():
    """10.3 -> 5.2 points gets back 49.5%, shown as 50%: it passes a pass ratio of 0.5; 49.4% (49%) does not."""
    half = ScoringPolicy(small_problem_threshold=3.0, pass_ratio=0.5, tolerance=1.0)
    assert judge_answer(10.3, 5.2, half) is True
    assert judge_answer(10.0, 5.06, half) is False  # 5.1 points shown: 49% got back.
    assert compare_with_actual(10.3, 5.2).recovered_ratio == pytest.approx(0.495, abs=0.001)


def test_policy_from_and_to_dict():
    """The rule is read from a dict, and written back to the same dict."""
    values = {"small_problem_threshold": 2.0, "pass_ratio": 0.9, "tolerance": 0.5, "max_answer_loss": 3.0}
    policy = ScoringPolicy.from_dict(values)
    assert policy == ScoringPolicy(2.0, 0.9, 0.5, 3.0)
    assert policy.to_dict() == values


def test_policy_from_dict_with_missing_and_unknown_keys():
    """Missing keys get the default values, and other keys of the quiz section are ignored."""
    assert ScoringPolicy.from_dict({"problems_per_game": 5}) == ScoringPolicy()


@pytest.mark.parametrize("values", [{"tolerance": "small"}, {"pass_ratio": 80}, {"max_answer_loss": -1}])
def test_policy_from_dict_with_wrong_values(values):
    """A value that is not a number, a ratio over 1 (such as 80 for 80%), or a negative limit is an error."""
    with pytest.raises(ValueError):
        ScoringPolicy.from_dict(values)
