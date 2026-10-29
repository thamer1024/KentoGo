"""Tests for kentogo.commentary.since."""

from datetime import datetime, timedelta

import pytest

from kentogo.commentary.since import (
    SINCE_ALL,
    SINCE_DATE,
    SINCE_MONTH,
    SINCE_THREE_MONTHS,
    SINCE_WEEK,
    parse_date,
    since_ns_for,
)

NOW = datetime(2026, 10, 23, 18, 0, 0)


def ns(moment: datetime) -> int:
    """Return a local time in nanoseconds."""
    return int(moment.timestamp() * 1_000_000) * 1000


@pytest.mark.parametrize("choice, days", [(SINCE_WEEK, 7), (SINCE_MONTH, 30), (SINCE_THREE_MONTHS, 91)])
def test_periods(choice, days):
    """A period goes back that many days from now."""
    assert since_ns_for(choice, NOW) == ns(NOW - timedelta(days=days))


def test_all_games():
    """All games: from the start of time."""
    assert since_ns_for(SINCE_ALL, NOW) == 0


def test_from_a_date():
    """Games changed on the date (from midnight) and later are shown."""
    since = since_ns_for(SINCE_DATE, NOW, "2026/10/1")
    assert since < ns(datetime(2026, 10, 1)) and since > ns(datetime(2026, 9, 30, 23, 59, 59))


@pytest.mark.parametrize("text", ["", "yesterday", "2026-13-01", "2026-12-01"])
def test_wrong_or_future_dates(text):
    """A date that cannot be read, or is in the future, is an error."""
    with pytest.raises(ValueError):
        since_ns_for(SINCE_DATE, NOW, text)


def test_unknown_choice():
    """An unknown choice is an error."""
    with pytest.raises(ValueError):
        since_ns_for("decade", NOW)


def test_parse_date():
    """Dates are read with "-", "/" or ".", with or without leading zeros."""
    assert parse_date("2026-10-01") == parse_date("2026/10/1") == parse_date(" 2026.10.01 ")
