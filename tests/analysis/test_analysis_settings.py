"""Tests for kentogo.analysis.analysis_settings."""

import pytest

from kentogo.analysis.analysis_settings import AnalysisSettings

KATRAIN_CONFIG = {
    "engine": {"max_visits": 2500, "fast_visits": 8, "max_time": 30.0},
    "trainer": {
        "eval_thresholds": [12, 6, 3, 1.5, 0.5, 0],
        "save_feedback": [True, True, True, False, False, False],
        "eval_show_ai": False,
        "save_marks": True,
        "save_analysis": False,  # Not copied: KentoGo always writes the analysis data.
    },
    "general": {"lang": "jp", "load_fast_analysis": True},
}


def test_defaults_are_katrains():
    settings = AnalysisSettings()
    assert settings.eval_thresholds == (12.0, 6.0, 3.0, 1.5, 0.5, 0.0)
    assert settings.mistake_threshold() == 3.0  # The fourth from the end, as KaTrain's "mistakes only".
    assert (settings.reanalyze, settings.mistakes_only, settings.move_from, settings.move_to) == (False, False, 0, 0)


def test_copied_from_katrain():
    settings = AnalysisSettings.from_katrain(KATRAIN_CONFIG)
    assert (settings.fast, settings.fast_visits, settings.max_time) == (True, 8, 30.0)
    assert settings.save_feedback == (True, True, True, False, False, False)
    assert (settings.eval_show_ai, settings.save_marks, settings.language) == (False, True, "jp")
    assert AnalysisSettings.from_katrain({}) == AnalysisSettings()


def test_through_the_settings_file_and_back():
    settings = AnalysisSettings(games_folder="/games", reanalyze=True, mistakes_only=True, move_from=30, move_to=150)
    values = settings.to_dict()
    assert values["eval_thresholds"] == [12.0, 6.0, 3.0, 1.5, 0.5, 0.0]  # A list in JSON.
    assert AnalysisSettings.from_dict(values) == settings
    assert AnalysisSettings.from_dict({"max_time": 10}).max_time == 10.0  # An int is taken as a float.


@pytest.mark.parametrize(
    "values",
    [
        {"fast": "yes"},
        {"move_from": -1},
        {"fast_visits": 0},
        {"eval_thresholds": [3, 6, 12, 0]},  # Not the biggest first.
        {"eval_thresholds": [12, 6, 3]},  # Too short for "mistakes only".
        {"save_feedback": [True, False]},  # Not the same length as the thresholds.
        {"save_feedback": "all"},
    ],
)
def test_wrong_values(values):
    with pytest.raises(ValueError):
        AnalysisSettings.from_dict(values)
