"""The daily limit of the practice: how many problems (or games) are left today.

The day ends at midnight in the computer's time zone: the answers of the day are counted from
their time (see schedule.answer_day), so the limit is cleared at midnight.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime


def answered_on(times: Iterable[str], day: date) -> int:
    """Return how many answers were given on a day, from their times (ISO 8601, with the time zone)."""
    return sum(1 for time in times if datetime.fromisoformat(time).astimezone().date() == day)


def left_today(limit: int, done: int) -> int | None:
    """Return how many more may be asked today (None: no limit).

    Args:
        limit: The most in a day (0: no limit).
        done: How many were asked today already.
    """
    if limit == 0:
        return None
    return max(limit - done, 0)
