"""Tests for kentogo.seichi.seichi_settings."""

import pytest

from kentogo.seichi.seichi_settings import ORDER_NEWEST, ORDER_RANDOM, SeichiSettings


def test_defaults_and_round_trip():
    """By default the practice cannot be chosen, and the games come at random. The settings are written back."""
    default = SeichiSettings.from_dict({})
    assert default == SeichiSettings() and not default.use_seichi and default.order == ORDER_RANDOM
    values = {
        "use_seichi": True,
        "seichi_order": ORDER_NEWEST,
        "seichi_priority": "mix",
        "seichi_review_mode": "once",
        "seichi_review_streak": 2,
        "seichi_session_limit": 5,
        "seichi_step_seconds": 0.6,
        "seichi_daily_limit_off": True,
    }
    settings = SeichiSettings.from_dict({**values, "other": 1})
    assert settings.to_dict() == values and settings.once
    assert settings.daily_limit == 0 and SeichiSettings(session_limit=5).daily_limit == 5


@pytest.mark.parametrize(
    "values",
    [
        {"use_seichi": "yes"},
        {"seichi_order": "oldest"},
        {"seichi_priority": "all"},
        {"seichi_review_mode": "never"},
        {"seichi_review_streak": -1},
        {"seichi_session_limit": True},
        {"seichi_step_seconds": -0.1},
        {"seichi_step_seconds": "fast"},
    ],
)
def test_wrong_value(values):
    """A value of a wrong type, or not one of the allowed values, is an error."""
    with pytest.raises(ValueError):
        SeichiSettings.from_dict(values)


def test_step_seconds():
    """The time of the move of a stone is 0.2 seconds by default, and settings.json can change it."""
    assert SeichiSettings().step_seconds == 0.2
    assert SeichiSettings.from_dict({"seichi_step_seconds": 1}).step_seconds == 1.0
    assert SeichiSettings.from_dict({"seichi_step_seconds": 0}).step_seconds == 0.0
