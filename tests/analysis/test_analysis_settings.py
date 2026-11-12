"""Tests for kentogo.analysis.analysis_settings."""

import pytest

from kentogo.analysis.analysis_settings import AnalysisSettings

KATRAIN_CONFIG = {
    "engine": {"max_visits": 2500, "fast_visits": 8, "max_time": 30.0},  # max_time is KaTrain's way: not copied.
    "trainer": {
        "eval_thresholds": [12, 6, 3, 1.5, 0.5, 0],
        "save_feedback": [True, True, True, False, False, False],
        "eval_show_ai": False,
        "save_marks": True,
        "save_analysis": False,  # Not copied: KentoGo always writes the analysis data.
    },
    "general": {"lang": "jp", "load_fast_analysis": False},  # Not copied: the first analysis always uses fast_visits.
}


def test_defaults():
    settings = AnalysisSettings()
    assert (settings.fast_visits, settings.retries, settings.deep_visits, settings.deep_max_moves) == (4, 2, 0, 6)


def test_copied_from_katrain():
    settings = AnalysisSettings.from_katrain(KATRAIN_CONFIG)
    assert settings.fast_visits == 8  # KaTrain's comment settings are not copied.
    assert AnalysisSettings.from_katrain({}) == AnalysisSettings()


def test_through_the_settings_file_and_back():
    settings = AnalysisSettings(games_folder="/games", fast_visits=200, retries=1, deep_visits=3000)
    values = settings.to_dict()
    assert AnalysisSettings.from_dict(values) == settings
    old = {"katrain_compatible": True, "max_time": 10.0, "fast": False}  # Settings no longer used.
    old |= {"eval_thresholds": [12, 6], "save_feedback": [True], "save_marks": True, "language": "jp"}  # Comments.
    old |= {"reanalyze": True, "reanalyze_visits": 900, "mistakes_only": True, "move_from": 30, "move_to": 150}
    old |= {"reanalyze_threshold": 4, "area_readings": True, "end_reading": True, "pass_readings": True}
    old |= {"settled_lines": True, "settle_radius": 3, "settle_change": 0.5, "settle_step": 1, "settle_max_moves": 9}
    assert AnalysisSettings.from_dict(old) == AnalysisSettings() and not set(old) & set(AnalysisSettings().to_dict())


@pytest.mark.parametrize(
    "values",
    [
        {"fast_visits": "many"},
        {"retries": -1},
        {"fast_visits": 0},
    ],
)
def test_wrong_values(values):
    with pytest.raises(ValueError):
        AnalysisSettings.from_dict(values)


def test_deep_visits_are_a_number_of_their_own():
    """No number of visits is fixed in the code: 0 means the engine's own visits."""
    assert AnalysisSettings().deep_visits == 0
    assert AnalysisSettings.from_dict({"deep_visits": 4800}).deep_visits == 4800
    with pytest.raises(ValueError):
        AnalysisSettings.from_dict({"deep_visits": -1})


def test_the_most_moves_read_deeply():
    """6 moves of a game are read deeply by default; 0 means no limit, and a number below 0 is wrong."""
    assert AnalysisSettings().deep_max_moves == 6
    assert AnalysisSettings.from_dict({"deep_max_moves": 0}).deep_max_moves == 0
    with pytest.raises(ValueError):
        AnalysisSettings.from_dict({"deep_max_moves": -1})
