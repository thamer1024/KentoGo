"""Tests for kentogo.quiz.quiz_settings."""

import pytest

from kentogo.mistakes.extract import ExtractSettings
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.quiz_settings import ORDER_NEWEST, QuizSettings


def test_defaults():
    """Without values, all settings have their default values."""
    settings = QuizSettings.from_dict({})
    assert settings == QuizSettings()
    assert (settings.order, settings.rotate, settings.games_folder) == ("file_name", False, "")


def test_from_and_to_dict():
    """All settings are read from one flat dict, and written back to the same dict."""
    values = {
        "games_folder": "games",
        "order": "newest",
        "rotate": True,
        "swap_colors": True,
        "my_names": ["Taro"],
        "problems_per_game": 3,
        "min_points_lost": 2.5,
        "skip_opening_moves": 0,
        "include_undone_moves": True,
        "decided_winrate": 99.0,
        "decided_lead": 40.0,
        "small_problem_threshold": 2.0,
        "pass_ratio": 0.9,
        "tolerance": 0.5,
    }
    settings = QuizSettings.from_dict(values)
    assert settings.order == ORDER_NEWEST
    assert settings.extract == ExtractSettings(("Taro",), 3, 2.5, 0, True)
    assert settings.scoring == ScoringPolicy(2.0, 0.9, 0.5)
    assert settings.to_dict() == values


@pytest.mark.parametrize(
    "values",
    [
        {"order": "oldest"},
        {"rotate": "yes"},
        {"games_folder": 5},
        {"problems_per_game": "many"},
        {"pass_ratio": 80},
    ],
)
def test_wrong_values(values):
    """Wrong values in any part of the quiz settings are errors."""
    with pytest.raises(ValueError):
        QuizSettings.from_dict(values)


def test_review_keys_are_ignored():
    """The review settings in the same dict belong to review.review_settings and are ignored here."""
    assert QuizSettings.from_dict({"priority": "mix", "review_streak": "x"}) == QuizSettings()
