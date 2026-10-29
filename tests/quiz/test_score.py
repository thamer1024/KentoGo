"""Tests for kentogo.quiz.score."""

import pytest

from kentogo.quiz.score import compare_with_actual, score_answer


@pytest.mark.parametrize(
    ("actual_loss", "answer_loss", "expected"),
    [
        (10.0, 1.0, 0.9),  # The example in the plan: 90% gets back.
        (10.0, 0.0, 1.0),  # The best move.
        (10.0, 10.0, 0.0),  # The same as the game move.
        (10.0, 15.0, 0.0),  # Worse than the game move.
        (10.0, -0.3, 1.0),  # Slightly better than the best move (noise).
        (0.0, 0.0, 1.0),  # The game move was already the best.
        (0.0, 1.0, 0.0),
    ],
)
def test_score_answer(actual_loss, answer_loss, expected):
    """The score is the part of the loss that the answer gets back, from 0 to 1."""
    assert score_answer(actual_loss, answer_loss) == pytest.approx(expected)


def test_compare_with_actual():
    """The comparison has both losses, the improvement and the score."""
    comparison = compare_with_actual(8.5, 1.2)
    assert comparison.actual_loss == 8.5
    assert comparison.answer_loss == 1.2
    assert comparison.improvement == pytest.approx(7.3)
    assert comparison.recovered_ratio == pytest.approx(7.3 / 8.5)


def test_compare_with_a_worse_answer():
    """A worse answer has a negative improvement and a score of 0."""
    comparison = compare_with_actual(4.0, 6.0)
    assert comparison.improvement == pytest.approx(-2.0)
    assert comparison.recovered_ratio == 0.0
