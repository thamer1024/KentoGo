"""Offer to raise or lower the pass ratio to suit how well the user answers (合格ラインの上げ下げの提案).

The measure is the average part of the loss got back (see quiz.score.score_answer) in the latest
WINDOW answers to normal problems (small problems are judged in another way, so they are left out):

- raise by STEP (at most MAX_RATIO) when the average is at least the next ratio + RAISE_MARGIN
  (for 70% -> 80%, an average of 85% or more);
- lower by STEP (at least MIN_RATIO) when the average is below the current ratio - LOWER_MARGIN
  (for 70% -> 60%, an average below 60%), for example when the stages bring harder problems.

The gap between the two keeps the ratio from going up and down by chance. Only the question is
made here: the answers in the history are never changed, and a problem that was finished stays
finished (its state comes from the judgment saved with each answer, see repetition.schedule).
After the user answers (yes or no), the app asks again only after WINDOW more answers
(QuizSettings.ratio_asked_at), so that the next offer is made from answers judged with the ratio
used then.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.score import score_answer

WINDOW = 30  # How many of the latest answers to normal problems are used.
STEP = 0.1  # How much the ratio is raised or lowered at a time.
RAISE_MARGIN = 0.05  # The average must be this much above the next ratio to raise it.
LOWER_MARGIN = 0.10  # The average must be this much below the current ratio to lower it.
MAX_RATIO = 0.9  # The ratio is never offered above this.
MIN_RATIO = 0.5  # The ratio is never offered below this.


class JudgedAnswer(Protocol):
    """An answer with its losses, such as review.record.AnswerRecord. Nothing else is needed."""

    actual_loss: float | None
    answer_loss: float | None


@dataclass(frozen=True)
class RatioOffer:
    """A proposal to change the pass ratio.

    Attributes:
        current: The pass ratio used now (0.0 to 1.0).
        proposed: The pass ratio offered (higher or lower than current).
        average: The average part of the loss got back in the latest answers (0.0 to 1.0).
        total: How many answers the average is made from.
    """

    current: float
    proposed: float
    average: float
    total: int

    @property
    def raises(self) -> bool:
        """Return True if the offer raises the ratio."""
        return self.proposed > self.current


def judged(answers: Sequence[JudgedAnswer]) -> list[JudgedAnswer]:
    """Return the answers with both losses known (the others cannot be measured), in the same order."""
    return [answer for answer in answers if answer.actual_loss is not None and answer.answer_loss is not None]


def find_ratio_offer(answers: Sequence[JudgedAnswer], policy: ScoringPolicy) -> RatioOffer | None:
    """Return the offer to raise or lower the pass ratio, or None if nothing should be asked.

    Args:
        answers: The answers with both losses known, the oldest first (see judged).
        policy: The rule used now.
    """
    normal = [answer for answer in answers if answer.actual_loss >= policy.small_problem_threshold]
    latest = normal[-WINDOW:]
    if len(latest) < WINDOW:
        return None
    average = round(sum(score_answer(a.actual_loss, a.answer_loss) for a in latest) / len(latest), 4)
    higher, lower = round(policy.pass_ratio + STEP, 2), round(policy.pass_ratio - STEP, 2)
    if higher <= MAX_RATIO and average >= round(higher + RAISE_MARGIN, 4):
        return RatioOffer(policy.pass_ratio, higher, average, len(latest))
    if lower >= MIN_RATIO and average < round(policy.pass_ratio - LOWER_MARGIN, 4):
        return RatioOffer(policy.pass_ratio, lower, average, len(latest))
    return None


def may_ask(enabled: bool, judged_count: int, asked_at: int) -> bool:
    """Return True if an offer may be asked now.

    Args:
        enabled: The setting that turns the offers on.
        judged_count: How many answers with both losses known there are in the history now.
        asked_at: How many there were when the user last answered an offer (0 if never).
    """
    return enabled and judged_count - asked_at >= WINDOW
