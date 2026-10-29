"""Tests for kentogo.repetition.schedule."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from kentogo.repetition.schedule import (
    DONE,
    INTERVAL_DAYS,
    NEW,
    STATE_REVIEW,
    ReviewState,
    answer_day,
    next_state,
    review_state,
    wait_days,
)
from kentogo.review.record import LOSS_FROM_SGF, AnswerRecord

DAY = date(2026, 10, 20)

RECORD = AnswerRecord("p1", "", "g.sgf", 3, "B", "R4", "A19", "Q4", 1.0, 8.0, LOSS_FROM_SGF, None, True, 0, False)


def answered(day: date, correct: bool | None) -> AnswerRecord:
    """Make a record of an answer at noon of a day, in the computer's time zone."""
    when = datetime(day.year, day.month, day.day, 12).astimezone()
    return replace(RECORD, answered_at=when.isoformat(timespec="seconds"), correct=correct)


def after(days: int) -> date:
    """Return the day the given number of days after DAY."""
    return DAY + timedelta(days=days)


def test_new_problem():
    """A problem without judged answers is new."""
    assert review_state([], 2) == NEW
    assert review_state([answered(DAY, None)], 2) == NEW


def test_correct_answers_in_a_row_finish_the_problem():
    """With 2, a problem answered correctly the first time is asked once more, 3 days later, and then it is done."""
    first = review_state([answered(DAY, True)], 2)
    assert first == ReviewState(STATE_REVIEW, 1, after(3))
    assert not first.is_due(DAY) and not first.is_due(after(2)) and first.is_due(after(3))
    assert review_state([answered(DAY, True), answered(after(3), True)], 2) == DONE


def test_a_wrong_answer_is_asked_the_next_day_not_the_same_day():
    """A wrong answer is asked again the next day, and stays due on later days until it is answered."""
    state = review_state([answered(DAY, False)], 2)
    assert state == ReviewState(STATE_REVIEW, 0, after(1))
    assert not state.is_due(DAY)
    assert state.is_due(after(1)) and state.is_due(after(5))  # A day that was missed is still due.


def test_a_wrong_answer_counts_the_correct_answers_again():
    """After a wrong answer, the correct answers are counted again from 0: 1 day, then 3 days, then done."""
    records = [answered(DAY, True), answered(after(3), False)]
    assert review_state(records, 2) == ReviewState(STATE_REVIEW, 0, after(4))
    records.append(answered(after(4), True))
    assert review_state(records, 2) == ReviewState(STATE_REVIEW, 1, after(7))
    records.append(answered(after(7), True))
    assert review_state(records, 2) == DONE


def test_the_wait_gets_longer_with_each_correct_answer():
    """Each correct answer in a row makes the wait longer: 3, 7, 14 days."""
    state = NEW
    days = [0]
    for _ in range(3):
        state = next_state(state, True, after(days[-1]), 5)
        days.append((state.due - DAY).days)
    assert days == [0, 3, 10, 24]


def test_the_problem_is_done_whatever_the_curve_says():
    """The required count finishes the problem, even if the curve has longer waits left."""
    records = [answered(DAY, False), answered(after(1), True), answered(after(4), True), answered(after(11), True)]
    assert review_state(records, 3) == DONE
    assert review_state(records, 4) == ReviewState(STATE_REVIEW, 3, after(25))


@pytest.mark.parametrize(("streak", "days"), [(0, 1), (1, 3), (2, 7), (5, 60), (8, 60)])
def test_wait_days(streak, days):
    """The wait after a wrong answer is 1 day; after the last wait in the list, the last one is used again."""
    assert wait_days(streak) == days == INTERVAL_DAYS[min(streak, len(INTERVAL_DAYS) - 1)]


def test_answers_not_judged_are_not_counted():
    """An answer that could not be judged does not change the review."""
    records = [answered(DAY, False), answered(after(1), None)]
    assert review_state(records, 2) == review_state(records[:1], 2)


def test_no_reviews():
    """With 0 required answers, a problem is never asked again, answered wrong or correctly."""
    assert review_state([answered(DAY, False)], 0) == DONE
    assert review_state([answered(DAY, True)], 0) == DONE


def test_once_mode():
    """In the "once" mode, one correct answer finishes the problem; a wrong one is asked the next day."""
    assert review_state([answered(DAY, True)], 3, once=True) == DONE
    wrong = [answered(DAY, False)]
    assert review_state(wrong, 3, once=True) == ReviewState(STATE_REVIEW, 0, after(1))
    assert review_state([*wrong, answered(after(1), True)], 3, once=True) == DONE
    assert review_state(wrong, 0, once=True).state == STATE_REVIEW  # The count of the settings is not used.


def test_a_problem_done_stays_done_when_answered_correctly():
    """A correct answer after the problem was done (for example, asked by hand) does not start it again."""
    assert next_state(DONE, True, DAY, 2) == DONE
    assert next_state(DONE, False, DAY, 2) == ReviewState(STATE_REVIEW, 0, after(1))


def test_last_wrong():
    """Only a problem waiting after a wrong answer is marked as answered wrong last time."""
    assert review_state([answered(DAY, False)], 2).last_wrong
    assert not review_state([answered(DAY, True)], 2).last_wrong
    assert not NEW.last_wrong and not DONE.last_wrong


def test_answer_day_uses_the_local_time_zone():
    """The day of an answer is the day in the computer's time zone, not in UTC."""
    when = datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)
    record = replace(RECORD, answered_at=when.isoformat())
    assert answer_day(record) == when.astimezone().date()
