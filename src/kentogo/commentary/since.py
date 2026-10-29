"""The time from which changed games are shown in the list of new games, chosen at the first run.

Before the first run, the history has no such time (see CommentaryHistory.since_ns). The
screen asks the user how far back to go: one week, one month, three months, all games, or
from a date. This module turns the choice into the time, without Kivy.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

SINCE_WEEK = "week"
SINCE_MONTH = "month"
SINCE_THREE_MONTHS = "three_months"
SINCE_ALL = "all"
SINCE_DATE = "date"  # From a date that the user writes, such as 2026-10-01.
SINCE_CHOICES = (SINCE_WEEK, SINCE_MONTH, SINCE_THREE_MONTHS, SINCE_ALL, SINCE_DATE)

_DAYS = {SINCE_WEEK: 7, SINCE_MONTH: 30, SINCE_THREE_MONTHS: 91}


def since_ns_for(choice: str, now: datetime, date_text: str = "") -> int:
    """Return the time (in nanoseconds since the epoch) from which changed games are shown.

    Args:
        choice: One of SINCE_CHOICES.
        now: The current local time.
        date_text: The date for SINCE_DATE, as YYYY-MM-DD (also with "/" or "."). The games
            changed on that day and later are shown.

    Returns:
        The time. 0 for SINCE_ALL, so that every game is shown.

    Raises:
        ValueError: If the choice is unknown, or the date cannot be read or is in the future.
    """
    if choice == SINCE_ALL:
        return 0
    if choice in _DAYS:
        return _ns(now - timedelta(days=_DAYS[choice]))
    if choice == SINCE_DATE:
        day = parse_date(date_text)
        if day > now.date():
            raise ValueError(f"the date is in the future: {date_text}")
        return _ns(datetime.combine(day, time()) - timedelta(microseconds=1))
    raise ValueError(f"unknown choice: {choice!r}")


def parse_date(text: str) -> date:
    """Read a date written as YYYY-MM-DD, YYYY/MM/DD or YYYY.MM.DD.

    Raises:
        ValueError: If the text is not such a date.
    """
    cleaned = text.strip().replace("/", "-").replace(".", "-")
    return date.fromisoformat("-".join(part.zfill(2) for part in cleaned.split("-")))


def _ns(moment: datetime) -> int:
    """Return a local time as nanoseconds since the epoch."""
    return int(moment.timestamp() * 1_000_000) * 1000
