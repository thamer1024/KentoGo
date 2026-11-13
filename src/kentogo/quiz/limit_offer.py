"""Offer to set or lower the limit of a correct answer's loss (正解とする上限の損の提案).

A beginner starts without a limit (ScoringPolicy.max_answer_loss is 0): in a big problem, an answer is
correct when it gets back enough of the loss, even when it still loses many points. As the user gets
stronger, the correct answers lose fewer points, and the app offers a limit, one step at a time: the
quiz setting limit_steps (LIMITS by default: no limit -> 12 -> 8 -> 5 -> 3 points).

The measure is the latest answers to normal problems, as many as the quiz setting offer_window (as in
quiz.ratio_offer; small problems are judged in another way), judged again with the rule used now. The
next limit is offered when:

- at least MIN_CORRECT_SHARE of them are correct;
- the average loss of the correct answers is below the next limit;
- at least MOST_SHARE of the correct answers lose no more than the next limit: most of them would still
  be correct with it, so it does not make the problems much harder at once.

The losses are taken as the screen shows them (rounded to 0.1 points, see quiz.judge). As with the
offers of the pass ratio, the answers in the history are never changed, and the app asks again only after
offer_window more answers (QuizSettings.limit_asked_at).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from kentogo.quiz.judge import ScoringPolicy, judge_answer
from kentogo.quiz.ratio_offer import WINDOW, JudgedAnswer
from kentogo.quiz.score import LOSS_DIGITS

LIMITS = (12.0, 8.0, 5.0, 3.0)  # The limits offered one after another (points), by default (QuizSettings.limit_steps).
MIN_CORRECT_SHARE = 1 / 3  # The part of the latest answers that must be correct for an offer (10 of 30).
MOST_SHARE = 0.8  # The part of the correct answers that must lose no more than the next limit.


@dataclass(frozen=True)
class LimitOffer:
    """A proposal to set or lower the limit of a correct answer's loss.

    Attributes:
        current: The limit used now (points; 0: no limit).
        proposed: The limit offered.
        average: The average loss of the correct answers among the latest answers (points).
        correct: How many of the latest answers are correct.
        total: How many latest answers were judged.
    """

    current: float
    proposed: float
    average: float
    correct: int
    total: int


def next_limit(current: float, limits: Sequence[float] = LIMITS) -> float | None:
    """Return the next of the limits (the biggest first) after the one used now (0: no limit), or None after the last."""
    return next((limit for limit in limits if current == 0 or limit < current), None)


def find_limit_offer(
    answers: Sequence[JudgedAnswer], policy: ScoringPolicy, window: int = WINDOW, limits: Sequence[float] = LIMITS
) -> LimitOffer | None:
    """Return the offer to set or lower the limit, or None if nothing should be asked (see the module).

    Args:
        answers: The answers with both losses known, the oldest first (see quiz.ratio_offer.judged).
        policy: The rule used now.
        window: How many of the latest answers to normal problems are used (1 or more).
        limits: The limits offered one after another, the biggest first (none: no offer).
    """
    normal = [answer for answer in answers if answer.actual_loss >= policy.small_problem_threshold]
    latest = normal[-window:]
    proposed = next_limit(policy.max_answer_loss, limits)
    if len(latest) < window or proposed is None:
        return None
    correct = [answer for answer in latest if judge_answer(answer.actual_loss, answer.answer_loss, policy)]
    if len(correct) < math.ceil(window * MIN_CORRECT_SHARE):
        return None
    losses = [max(round(answer.answer_loss, LOSS_DIGITS), 0.0) for answer in correct]
    average = round(sum(losses) / len(losses), LOSS_DIGITS)
    within = sum(loss <= proposed for loss in losses) / len(losses)
    if average < proposed and within >= MOST_SHARE:
        return LimitOffer(policy.max_answer_loss, proposed, average, len(correct), len(latest))
    return None
