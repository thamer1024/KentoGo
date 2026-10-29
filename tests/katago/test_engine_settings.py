"""Tests for kentogo.katago.engine_settings."""

import pytest

from kentogo.katago.engine_settings import JUDGE_COMPARE, EngineSettings

VALUES = {
    "use_katago": False,
    "katago": "bin/katago",
    "model": "models/b18.bin.gz",
    "humanlike_model": "models/human.bin.gz",
    "config": "katago/analysis.cfg",
    "max_visits": 2500,
    "wide_root_noise": 0.04,
    "katrain_config": "settings/katrain-config.json",
    "katrain_folder": "C:/Program Files/KaTrain",
    "compare_model": "models/normal.bin.gz",
    "use_compare": True,
    "compare_max_visits": 200,
    "judge_model": "compare",
    "estimate_visits": 50,
}


def test_defaults():
    """By default KataGo is used, the paths are empty, and KaTrain's settings are in the usual place."""
    settings = EngineSettings.from_dict({})
    assert settings.use_katago is True
    assert (settings.katago, settings.model, settings.max_visits) == ("", "", 500)
    assert settings.katrain_config == "~/.katrain/config.json"


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
        {"compare_max_visits": 0},
        {"estimate_visits": 0},
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
    }
    settings = EngineSettings.from_katrain(katrain, "~/.katrain/config.json")
    assert settings.use_katago is True
    assert (settings.katago, settings.model, settings.config) == (
        "bin/katago",
        "/models/human.bin.gz",
        "/katago/analysis.cfg",
    )
    assert (settings.max_visits, settings.wide_root_noise) == (2500, 0.04)


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


def test_comparison_model():
    """The comparison model has its own switch, and runs without the human-like model."""
    settings = EngineSettings.from_dict(
        {"model": "/h.bin.gz", "humanlike_model": "/h.bin.gz", "compare_model": "/n.bin.gz", "use_compare": True}
    )
    assert settings.compare_on and settings.judge_model == "main"
    assert settings.compare_engine()["model"] == "/n.bin.gz"
    assert settings.compare_engine()["humanlike_model"] == ""
    # Each model has its own visits.
    assert (settings.max_visits, settings.compare_engine()["max_visits"]) == (500, 500)
    assert EngineSettings(max_visits=2500, compare_max_visits=100).compare_engine()["max_visits"] == 100
    assert not EngineSettings(use_compare=True).compare_on  # No model set.
    assert not EngineSettings(compare_model="/n.bin.gz").compare_on  # Turned off.
    judged = EngineSettings.from_dict({"judge_model": "compare"})
    assert judged.judge_model == JUDGE_COMPARE
    assert EngineSettings.from_dict(judged.to_dict()) == judged
    for wrong in ({"judge_model": "other"}, {"use_compare": "yes"}, {"compare_model": 3}):
        with pytest.raises(ValueError):
            EngineSettings.from_dict(wrong)


def test_models_differ():
    """Only a comparison model that is turned on and is another file differs from the main model."""
    main = EngineSettings(model="~/models/b18.bin.gz", compare_model="~/models/b28.bin.gz", use_compare=True)
    assert main.models_differ
    assert not EngineSettings(
        model="~/models/b18.bin.gz", compare_model=" ~/models/b18.bin.gz ", use_compare=True
    ).models_differ
    assert not EngineSettings(model="~/models/b18.bin.gz", compare_model="~/models/b28.bin.gz").models_differ
