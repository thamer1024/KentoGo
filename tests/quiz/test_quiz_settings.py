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
        "loss_stages": [],
        "punish_opponent_loss": 15.0,
        "punish_my_loss": 5.0,
        "small_problem_threshold": 2.0,
        "pass_ratio": 0.9,
        "tolerance": 0.5,
        "max_answer_loss": 0.0,
        "ratio_offer": False,
        "ratio_asked_at": 40,
        "limit_asked_at": 70,
        "offer_window": 20,
        "limit_steps": [10.0, 4.0],
        "problem_kind": "punish",
    }
    settings = QuizSettings.from_dict(values)
    assert settings.order == ORDER_NEWEST
    assert settings.extract == ExtractSettings(("Taro",), 3, 2.5, 0, True)
    assert settings.scoring == ScoringPolicy(2.0, 0.9, 0.5)
    assert settings.to_dict() == values


def test_the_limit_steps_are_kept_the_biggest_first():
    """The steps are kept the biggest first, without repeats."""
    assert QuizSettings.from_dict({"limit_steps": [3, 12, 8, 8]}).limit_steps == (12.0, 8.0, 3.0)
    assert QuizSettings().offer_window == 30 and QuizSettings().limit_steps == (12.0, 8.0, 5.0, 3.0)


@pytest.mark.parametrize(
    "values",
    [
        {"order": "oldest"},
        {"rotate": "yes"},
        {"games_folder": 5},
        {"problems_per_game": "many"},
        {"pass_ratio": 80},
        {"ratio_asked_at": -1},
        {"limit_asked_at": -1},
        {"offer_window": 0},
        {"limit_steps": [8, 0]},
        {"limit_steps": "12,8"},
        {"ratio_offer": "yes"},
    ],
)
def test_wrong_values(values):
    """Wrong values in any part of the quiz settings are errors."""
    with pytest.raises(ValueError):
        QuizSettings.from_dict(values)


def test_review_keys_are_ignored():
    """The review settings in the same dict belong to review.review_settings and are ignored here."""
    assert QuizSettings.from_dict({"priority": "mix", "review_streak": "x"}) == QuizSettings()


def test_wrong_problem_kind():
    with pytest.raises(ValueError):
        QuizSettings.from_dict({"problem_kind": "easy"})
