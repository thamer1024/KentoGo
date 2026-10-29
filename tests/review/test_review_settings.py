"""Tests for kentogo.review.review_settings."""

import pytest

from kentogo.repetition.modes import PRIORITY_MIX, PRIORITY_NEW, REVIEW_ONCE
from kentogo.review.review_settings import ReviewSettings


def test_defaults():
    """Without values, the settings have their default values, and quiz keys are ignored."""
    settings = ReviewSettings.from_dict({"order": "newest", "rotate": True})
    assert settings == ReviewSettings()
    assert (settings.review_mode, settings.review_streak, settings.priority, settings.session_limit) == (
        "curve",
        2,
        PRIORITY_NEW,
        20,
    )


def test_from_and_to_dict():
    """The settings are read from the flat dict and written back."""
    values = {
        "review_mode": "once",
        "review_streak": 2,
        "priority": "mix",
        "session_limit": 30,
        "daily_limit_off": False,
    }
    settings = ReviewSettings.from_dict(values)
    assert (settings.review_mode, settings.priority) == (REVIEW_ONCE, PRIORITY_MIX)
    assert settings.to_dict() == values and settings.daily_limit == 30


def test_the_daily_limit_can_be_turned_off():
    """daily_limit_off (only in settings.json, for tests) asks without the limit."""
    assert ReviewSettings.from_dict({"session_limit": 30, "daily_limit_off": True}).daily_limit == 0


@pytest.mark.parametrize(
    "values",
    [
        {"priority": "old"},
        {"review_mode": "x"},
        {"review_streak": -1},
        {"review_streak": "3"},
        {"session_limit": -5},
        {"session_limit": True},
        {"daily_limit_off": "yes"},
    ],
)
def test_wrong_values(values):
    """Wrong values are errors."""
    with pytest.raises(ValueError):
        ReviewSettings.from_dict(values)
