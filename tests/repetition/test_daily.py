"""Tests for kentogo.repetition.daily."""

from datetime import date, datetime

from kentogo.repetition.daily import answered_on, left_today


def test_answers_are_counted_by_the_local_day():
    """The day of an answer is its day in the computer's time zone: the count starts again at midnight."""
    times = [
        datetime(2026, 10, 28, 23, 59).astimezone().isoformat(),
        datetime(2026, 10, 28, 0, 0).astimezone().isoformat(),
        datetime(2026, 10, 27, 23, 59).astimezone().isoformat(),
    ]
    assert answered_on(times, date(2026, 10, 28)) == 2
    assert answered_on(times, date(2026, 10, 29)) == 0


def test_left_today():
    """The limit less the answers of the day; 0 is no limit."""
    assert left_today(5, 2) == 3
    assert left_today(5, 7) == 0
    assert left_today(0, 7) is None
