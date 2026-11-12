"""Tests for kentogo.katago.engine_settings."""

import pytest

from kentogo.katago.engine_settings import EngineSettings

VALUES = {
    "use_katago": False,
    "katago": "bin/katago",
    "model": "models/b18.bin.gz",
    "humanlike_model": "models/human.bin.gz",
    "config": "katago/analysis.cfg",
    "max_visits": 2500,
    "wide_root_noise": 0.04,
    "max_time": 12.0,
    "katrain_config": "settings/katrain-config.json",
    "katrain_folder": "C:/Program Files/KaTrain",
    "estimate_visits": 50,
    "ready_timeout": 1200.0,
}


def test_defaults():
    """By default KataGo is used, the paths are empty, and KaTrain's settings are in the usual place."""
    settings = EngineSettings.from_dict({})
    assert settings.use_katago is True
    assert (settings.katago, settings.model, settings.max_visits) == ("", "", 500)
    assert settings.katrain_config == "~/.katrain/config.json"
    assert settings.max_time == 8.0  # KaTrain's default time limit.


def test_from_and_to_dict():
    """The settings are read from a dict, and written back to the same dict."""
    assert EngineSettings.from_dict(VALUES).to_dict() == VALUES


@pytest.mark.parametrize(
    "values",
    [
        {"use_katago": "no"},
        {"model": None},
        {"max_visits": "many"},
        {"max_visits": 0},
        {"estimate_visits": 0},
        {"ready_timeout": 0},
        {"ready_timeout": "long"},
        {"max_time": -1},
        {"max_time": "long"},
    ],
)
def test_wrong_values(values):
    """Wrong values are errors."""
    with pytest.raises(ValueError):
        EngineSettings.from_dict(values)


def test_from_katrain():
    """KaTrain's local engine settings are copied, and the other KaTrain settings are ignored."""
    katrain = {
        "backend": "local",
        "katago": "bin/katago",
        "model": "/models/human.bin.gz",
        "humanlike_model": "/models/human.bin.gz",
        "config": "/katago/analysis.cfg",
        "max_visits": 2500,
        "fast_visits": 4,
        "wide_root_noise": 0.04,
        "max_time": 5.0,
    }
    settings = EngineSettings.from_katrain(katrain, "~/.katrain/config.json")
    assert settings.use_katago is True
    assert (settings.katago, settings.model, settings.config) == (
        "bin/katago",
        "/models/human.bin.gz",
        "/katago/analysis.cfg",
    )
    assert (settings.max_visits, settings.wide_root_noise, settings.max_time) == (2500, 0.04, 5.0)


def test_katrain_engine():
    """The settings can be given to engine_command in the form of KaTrain's engine settings."""
    engine = EngineSettings.from_dict(VALUES).katrain_engine()
    assert engine == {
        "backend": "local",
        "katago": "bin/katago",
        "model": "models/b18.bin.gz",
        "humanlike_model": "models/human.bin.gz",
        "config": "katago/analysis.cfg",
        "max_visits": 2500,
    }


def test_settings_of_the_comparison_model_are_ignored():
    """The settings of the comparison model of older versions are ignored, as other unknown keys."""
    old = {"compare_model": "/n.bin.gz", "use_compare": True, "compare_max_visits": 200, "judge_model": "compare"}
    settings = EngineSettings.from_dict({**old, "max_visits": 300})
    assert settings == EngineSettings(max_visits=300)
    assert not set(old) & set(settings.to_dict())
