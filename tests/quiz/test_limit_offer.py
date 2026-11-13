"""Tests for kentogo.quiz.limit_offer."""

from dataclasses import dataclass

from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.limit_offer import LIMITS, LimitOffer, find_limit_offer, next_limit
from kentogo.quiz.ratio_offer import WINDOW

BEGINNER = ScoringPolicy(small_problem_threshold=3.0, pass_ratio=0.6, tolerance=1.0)


@dataclass(frozen=True)
class Answer:
    """An answer: only the losses."""

    actual_loss: float | None
    answer_loss: float | None


def big(answer_loss: float) -> Answer:
    """An answer to a 20-point problem."""
    return Answer(20.0, answer_loss)


def test_the_limits_come_one_after_another():
    """No limit -> 12 -> 8 -> 5 -> 3, and nothing after the last one."""
    assert [next_limit(current) for current in (0.0, 12.0, 8.0, 5.0, 3.0)] == [12.0, 8.0, 5.0, 3.0, None]
    assert next_limit(10.0) == 8.0 and LIMITS[0] == 12.0  # A limit of the user's own: the next smaller one.


def test_a_limit_is_offered_when_the_correct_answers_lose_less_than_it():
    """All 30 answers are correct, and lose 6 points on average: a limit of 12 is offered."""
    offer = find_limit_offer([big(4.0), big(8.0)] * (WINDOW // 2), BEGINNER)
    assert offer == LimitOffer(0.0, 12.0, 6.0, WINDOW, WINDOW)


def test_the_next_limit_after_the_one_used_now():
    """With a limit of 12, an average below 8 offers 8."""
    policy = ScoringPolicy(3.0, 0.6, 1.0, max_answer_loss=12.0)
    assert find_limit_offer([big(5.0)] * WINDOW, policy) == LimitOffer(12.0, 8.0, 5.0, WINDOW, WINDOW)


def test_no_offer_when_too_many_correct_answers_are_near_the_limit():
    """The average is below 12, but a quarter of the correct answers lose more than 12 points."""
    answers = [big(2.0)] * 22 + [Answer(40.0, 14.0)] * 8  # 14 of 40 points: correct (65% got back).
    assert find_limit_offer(answers, BEGINNER) is None  # The average is 5.2, but only 73% are within 12.


def test_no_offer_when_the_average_is_not_below_the_next_limit():
    """The correct answers lose 8 points on average: 8 is not offered with a limit of 12 (8 is not below 8)."""
    policy = ScoringPolicy(3.0, 0.6, 1.0, max_answer_loss=12.0)
    assert find_limit_offer([big(8.0)] * WINDOW, policy) is None


def test_no_offer_without_enough_answers_or_correct_answers():
    """Fewer than WINDOW answers to normal problems, or fewer than 10 correct ones."""
    assert find_limit_offer([big(2.0)] * (WINDOW - 1), BEGINNER) is None
    assert find_limit_offer([big(2.0)] * 9 + [big(19.0)] * (WINDOW - 9), BEGINNER) is None
    assert find_limit_offer([Answer(2.0, 0.5)] * WINDOW, BEGINNER) is None  # Small problems are left out.


def test_the_losses_are_taken_as_they_are_shown():
    """7.96 points is shown as 8.0, which is not below 8; 7.94 is shown as 7.9, which is."""
    policy = ScoringPolicy(3.0, 0.6, 1.0, max_answer_loss=12.0)
    assert find_limit_offer([big(7.96)] * WINDOW, policy) is None
    assert find_limit_offer([big(7.94)] * WINDOW, policy) == LimitOffer(12.0, 8.0, 7.9, WINDOW, WINDOW)


def test_the_window_and_the_limits_of_the_settings():
    """With 10 answers and the limits 10 and 4, a limit of 10 is offered from 10 answers, 4 of them correct."""
    answers = [big(2.0)] * 4 + [big(19.0)] * 6  # 4 correct, which is a third of 10 (rounded up).
    assert find_limit_offer(answers, BEGINNER, 10, (10.0, 4.0)) == LimitOffer(0.0, 10.0, 2.0, 4, 10)
    assert find_limit_offer(answers[1:], BEGINNER, 10, (10.0, 4.0)) is None  # Only 9 answers.
    assert find_limit_offer(answers, BEGINNER, 10, ()) is None  # No steps: no offer.
