"""Tests for kentogo.quiz.judge."""

import pytest

from kentogo.quiz.judge import ScoringPolicy, judge_answer

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


def test_policy_from_and_to_dict():
    """The rule is read from a dict, and written back to the same dict."""
    values = {"small_problem_threshold": 2.0, "pass_ratio": 0.9, "tolerance": 0.5}
    policy = ScoringPolicy.from_dict(values)
    assert policy == ScoringPolicy(2.0, 0.9, 0.5)
    assert policy.to_dict() == values


def test_policy_from_dict_with_missing_and_unknown_keys():
    """Missing keys get the default values, and other keys of the quiz section are ignored."""
    assert ScoringPolicy.from_dict({"problems_per_game": 5}) == ScoringPolicy()


@pytest.mark.parametrize("values", [{"tolerance": "small"}, {"pass_ratio": 80}])
def test_policy_from_dict_with_wrong_values(values):
    """A value that is not a number, or a ratio over 1 (such as 80 for 80%), is an error."""
    with pytest.raises(ValueError):
        ScoringPolicy.from_dict(values)
