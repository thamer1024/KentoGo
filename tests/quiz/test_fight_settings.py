"""Tests for kentogo.quiz.fight_settings."""

import pytest

from kentogo.app_settings import AppSettings
from kentogo.quiz.fight_judge import OPPONENT_RANK, OPPONENT_STRONG
from kentogo.quiz.fight_settings import FightSettings


def test_fight_settings():
    """The strongest opponent and 3 points at first; they are kept in the "fights" part with the reviews."""
    assert FightSettings() == FightSettings(OPPONENT_STRONG, 3.0)
    settings = AppSettings.from_sections(
        {"fights": {"opponent": OPPONENT_RANK, "score_tolerance": 2, "review_streak": 3}}
    )
    assert settings.fight_play == FightSettings(OPPONENT_RANK, 2.0) and settings.fights.review_streak == 3
    assert AppSettings.from_sections(settings.sections()) == settings
    with pytest.raises(ValueError):
        FightSettings.from_dict({"opponent": "other"})
    with pytest.raises(ValueError):
        FightSettings.from_dict({"score_tolerance": -1})
