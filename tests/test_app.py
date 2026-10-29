"""Tests for kentogo.app (the parts without Kivy)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from kentogo.app import (
    _make_setup,
    _settings_or_defaults,
    _SetupParts,
    load_settings,
    parse_arguments,
    read_language,
    save_language,
    save_settings,
)
from kentogo.app_settings import AppSettings
from kentogo.gui.texts import notice_text
from kentogo.katago.engine_settings import EngineSettings
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.record.katrain_comment import INTERNAL_MARKER
from kentogo.review.review_settings import ReviewSettings
from kentogo.seichi.seichi_settings import SeichiSettings

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def sgf_with_mistake(loss: float) -> str:
    """Make a game where black's second move loses the given points."""
    comment = (
        f"\nMove 3: B A19\nEstimated point loss: {loss:.1f}\nPredicted top move was Q4 (B+1.0).\nPV: BQ4\n"
        + INTERNAL_MARKER
    )
    return f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd];W[dp];B[aa]C[{comment}])"


def test_parse_arguments_defaults():
    """Without arguments, the folder comes from the settings in the usual place, and KataGo is used."""
    arguments = parse_arguments([])
    assert arguments.folder is None
    assert arguments.settings == Path("~/.kentogo/settings.json")
    assert arguments.no_katago is False


def test_parse_arguments_options(tmp_path):
    """A folder, another settings file, and turning KataGo off can be given."""
    arguments = parse_arguments([str(tmp_path), "--settings", "my.json", "--no-katago"])
    assert (arguments.folder, arguments.settings, arguments.no_katago) == (tmp_path, Path("my.json"), True)


def test_load_settings_makes_the_file(tmp_path):
    """Without a settings file, the default values are used and written to a new file.

    The engine settings are copied from KaTrain's config.json.
    """
    katrain_config = tmp_path / "config.json"
    katrain_config.write_text(json.dumps({"engine": {"model": "/m.bin.gz", "max_visits": 2500}}), encoding="utf-8")
    path = tmp_path / "kentogo" / "settings.json"
    settings = load_settings(path, katrain_config)
    quiz, engine = settings.quiz, settings.engine
    assert (quiz, settings.review) == (QuizSettings(), ReviewSettings())
    assert (engine.model, engine.max_visits, engine.katrain_config) == ("/m.bin.gz", 2500, str(katrain_config))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["quiz"]["order"] == "file_name"
    assert saved["quiz"]["session_limit"] == 20  # The review settings are in the same part as before.
    assert saved["engine"]["model"] == "/m.bin.gz"


def test_load_settings_without_katrain(tmp_path):
    """Without KaTrain's config.json, the engine settings get their default values."""
    assert load_settings(tmp_path / "settings.json", tmp_path / "missing.json").engine == EngineSettings()


def test_load_settings_reads_the_file(tmp_path):
    """Values in the settings file are used."""
    path = tmp_path / "settings.json"
    values = {"quiz": {"games_folder": "/games", "order": "random", "priority": "mix"}, "engine": {"use_katago": False}}
    path.write_text(json.dumps(values), encoding="utf-8")
    settings = load_settings(path)
    assert (settings.quiz.games_folder, settings.quiz.order, settings.engine.use_katago) == ("/games", "random", False)
    assert settings.review.priority == "mix"


def test_load_settings_with_a_wrong_value(tmp_path):
    """A wrong value in the settings file is an error."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"quiz": {"order": "oldest"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_save_settings_keeps_other_sections(tmp_path):
    """Saved settings are read back, and other sections of the file are kept."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"history": {"keep": 1}, "quiz": {"order": "random"}}))
    settings = AppSettings(
        QuizSettings(games_folder="/games", order="newest"),
        EngineSettings(katago="/bin/katago", katrain_config=str(tmp_path / "none.json")),
        ReviewSettings(priority="mix", session_limit=5),
        SeichiSettings(use_seichi=True),
    )
    save_settings(path, settings)
    assert json.loads(path.read_text())["history"] == {"keep": 1}
    assert load_settings(path, tmp_path / "none.json") == settings


def test_broken_settings_are_replaced_by_the_defaults(tmp_path):
    """A broken settings file does not stop the app: the defaults are used, and the user is told why."""
    path = tmp_path / "settings.json"
    path.write_text("{broken")
    notices = []
    settings = _settings_or_defaults(path, notices)
    assert settings.quiz == QuizSettings()
    assert len(notices) == 1 and "初期設定" in notice_text(notices[0])


def test_the_language_is_english_until_one_is_saved(tmp_path):
    """Without a saved language (or with a broken file or an unknown language) the screens are in English."""
    path = tmp_path / "settings.json"
    assert read_language(path) == "en"
    path.write_text("not json", encoding="utf-8")
    assert read_language(path) == "en"
    path.write_text(json.dumps({"general": {"language": "xx"}}), encoding="utf-8")
    assert read_language(path) == "en"


def test_save_language_keeps_the_other_settings(tmp_path):
    """The chosen language is kept in the "general" section; the other sections are not changed."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"quiz": {"order": "newest"}}), encoding="utf-8")
    assert save_language(path, "jp") == ""
    assert read_language(path) == "jp"
    assert json.loads(path.read_text(encoding="utf-8"))["quiz"] == {"order": "newest"}


def test_save_language_tells_why_it_failed(tmp_path):
    """A broken settings file is not replaced: the reason is returned to be shown."""
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert save_language(path, "jp") != ""
    assert path.read_text(encoding="utf-8") == "not json"


def test_setup_follows_the_settings_it_is_made_from(tmp_path):
    """The setup is made from the given settings, so new settings can be used without a new start."""
    import random

    arguments = parse_arguments(["--settings", str(tmp_path / "settings.json")])
    settings = AppSettings()
    on = replace(settings, seichi=replace(settings.seichi, use_seichi=True, step_seconds=0.7))
    parts = _SetupParts(arguments, on, None, None, random.Random(0), ())
    setup = _make_setup(parts, lambda _saved: None)
    assert setup.use_seichi and setup.seichi.step_seconds == 0.7
    off = _make_setup(replace(parts, settings=settings), lambda _saved: None)
    assert not off.use_seichi
