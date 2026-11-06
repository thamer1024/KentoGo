"""Tests for kentogo.quiz.ratio_offer."""

from dataclasses import dataclass

from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.ratio_offer import WINDOW, RatioOffer, find_ratio_offer, judged, may_ask

POLICY = ScoringPolicy(small_problem_threshold=3.0, pass_ratio=0.7, tolerance=1.0)


@dataclass(frozen=True)
class Answer:
    """An answer: only the losses."""

    actual_loss: float | None
    answer_loss: float | None


def got_back(part: float) -> Answer:
    """An answer to a 10-point problem that gets back the given part of the loss."""
    return Answer(10.0, round(10.0 * (1 - part), 6))


def test_raise_when_the_average_is_5_points_above_the_next_ratio():
    offer = find_ratio_offer([got_back(0.85)] * WINDOW, POLICY)
    assert offer == RatioOffer(0.7, 0.8, 0.85, WINDOW)
    assert offer.raises


def test_no_offer_between_the_two_limits():
    assert find_ratio_offer([got_back(0.84)] * WINDOW, POLICY) is None
    assert find_ratio_offer([got_back(0.6)] * WINDOW, POLICY) is None


def test_lower_when_the_average_is_10_points_below_the_ratio():
    offer = find_ratio_offer([got_back(0.55)] * WINDOW, POLICY)
    assert offer == RatioOffer(0.7, 0.6, 0.55, WINDOW)
    assert not offer.raises


def test_never_above_the_highest_or_below_the_lowest_ratio():
    assert find_ratio_offer([got_back(1.0)] * WINDOW, ScoringPolicy(pass_ratio=0.9)) is None
    assert find_ratio_offer([got_back(0.0)] * WINDOW, ScoringPolicy(pass_ratio=0.5)) is None


def test_only_the_latest_normal_answers_count():
    small = Answer(2.0, 2.0)  # A small problem (less than 3 points), left out.
    answers = [got_back(0.2)] * 10 + [got_back(0.9)] * WINDOW + [small] * 5
    assert find_ratio_offer(answers, POLICY) == RatioOffer(0.7, 0.8, 0.9, WINDOW)
    assert find_ratio_offer([got_back(0.9)] * (WINDOW - 1) + [small], POLICY) is None


def test_answers_without_losses_are_left_out():
    good, fair = got_back(0.9), got_back(0.7)
    assert judged([good, Answer(None, 1.0), Answer(5.0, None), fair]) == [good, fair]


def test_may_ask_again_after_enough_answers():
    assert may_ask(True, 45, 0)
    assert not may_ask(True, 45, 20)  # Only 25 answers since the last offer was answered.
    assert may_ask(True, 50, 20)
    assert not may_ask(False, 100, 0)
