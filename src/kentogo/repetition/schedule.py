"""Decide when a problem is asked again, along the forgetting curve.

A problem is done when it has been answered correctly required_streak times in a row (the first
answer counts too). Until then it is asked again on a later day, never the same day:

- after a wrong answer, the next day, and the correct answers are counted again from 0;
- after a correct answer, after a wait that gets longer with each correct answer in a row
  (INTERVAL_DAYS: 3, 7, 14 ... days).

With the "once" review mode, one correct answer is enough (required_streak is 1).

Answers that could not be judged are not counted. The waits are counted in calendar days of the
computer's time zone, so a problem answered wrong in the evening is asked again the next morning.

The state is worked out from all answers in the history every time, so nothing else has to be
saved, and a change of required_streak is used at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol


class Judged(Protocol):
    """One judged try, such as an answer to a quiz problem (review.record) or a game counted (seichi)."""

    answered_at: str  # When, in ISO 8601 format with the time zone.
    correct: bool | None  # Whether it went well, or None if it was not judged.


# The wait in days after a wrong answer (the first), and after each correct answer in a row.
# After the last one, the last wait is used again.
INTERVAL_DAYS = (1, 3, 7, 14, 30, 60)

# States of a problem.
STATE_NEW = "new"  # Never judged.
STATE_REVIEW = "review"  # Asked again on a later day: not yet answered correctly enough times in a row.
STATE_DONE = "done"  # Answered correctly required_streak times in a row.


@dataclass(frozen=True)
class ReviewState:
    """Where a problem is in the review.

    Attributes:
        state: STATE_NEW, STATE_REVIEW or STATE_DONE.
        streak: Correct answers in a row since the last wrong answer (0 right after a wrong answer).
        due: The day when the problem is asked again (only for STATE_REVIEW), else None.
    """

    state: str
    streak: int = 0
    due: date | None = None

    def is_due(self, today: date) -> bool:
        """Return True if the problem is reviewed today (its day has come)."""
        return self.state == STATE_REVIEW and self.due is not None and self.due <= today

    @property
    def last_wrong(self) -> bool:
        """True if the last answer was wrong (such problems are asked first among the reviews)."""
        return self.state == STATE_REVIEW and self.streak == 0


NEW = ReviewState(STATE_NEW)
DONE = ReviewState(STATE_DONE)


def review_state(records: list[Judged], required_streak: int, once: bool = False) -> ReviewState:
    """Work out the state of a problem from its answers.

    Args:
        records: All answers to the problem, the oldest first.
        required_streak: How many correct answers in a row finish the review.
            0 means that problems are never reviewed (not used when once is True).
        once: True for the "once" review mode: one correct answer finishes the review.

    Returns:
        The state after the last judged answer.
    """
    required = 1 if once else required_streak
    state = NEW
    for record in records:
        if record.correct is None:
            continue  # Not judged: not counted.
        state = next_state(state, record.correct, answer_day(record), required)
    return state


def next_state(state: ReviewState, correct: bool, day: date, required_streak: int) -> ReviewState:
    """Return the state after one judged answer.

    Args:
        state: The state before the answer.
        correct: Whether the answer was correct.
        day: The day of the answer.
        required_streak: How many correct answers in a row finish the review (0: never reviewed).
    """
    if state.state == STATE_DONE and correct:
        return DONE
    streak = state.streak + 1 if correct else 0
    if required_streak <= 0 or streak >= required_streak:
        return DONE
    return ReviewState(STATE_REVIEW, streak, day + timedelta(days=wait_days(streak)))


def wait_days(streak: int) -> int:
    """Return the days to wait before the next question, after an answer that leaves this streak."""
    return INTERVAL_DAYS[min(streak, len(INTERVAL_DAYS) - 1)]


def answer_day(record: Judged) -> date:
    """Return the day of an answer in the computer's time zone."""
    return datetime.fromisoformat(record.answered_at).astimezone().date()
