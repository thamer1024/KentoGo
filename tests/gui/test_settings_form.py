"""Tests for kentogo.gui.settings_form."""

import json
from dataclasses import replace

import pytest

from kentogo.app_settings import AppSettings
from kentogo.gui.settings_form import (
    FIELDS,
    KIND_FILE,
    KIND_FOLDER,
    PAGE_GROUPS,
    PAGES,
    FormError,
    count_games,
    form_values,
    needs_rereading,
    path_exists,
    settings_from_form,
    values_from_katrain,
)
from kentogo.katago.engine_settings import EngineSettings
from kentogo.katago.locate import KataGoNotFoundError
from kentogo.mistakes.extract import ExtractSettings
from kentogo.quiz.quiz_settings import QuizSettings

QUIZ = QuizSettings(games_folder="/games", extract=ExtractSettings(my_names=("Taro", "太郎")))
ENGINE = EngineSettings(katago="/bin/katago", max_visits=2500)
SETTINGS = AppSettings(QUIZ, ENGINE)


def test_every_field_is_a_setting():
    """Every input of the form is a key of a part of the settings file."""
    sections = AppSettings().sections()
    for spec in FIELDS:
        assert spec.key in sections[spec.section]
    assert len({spec.id for spec in FIELDS}) == len(FIELDS)  # The AI's "model" has its own name on the form.


def test_form_values():
    """Settings are shown as texts, names joined with commas, and check boxes as True/False."""
    values = form_values(SETTINGS)
    assert values["games_folder"] == "/games"
    assert values["my_names"] == "Taro, 太郎"
    assert values["max_visits"] == "2500"
    assert values["use_katago"] is True
    assert values["order"] == "file_name"


def test_unchanged_form_gives_the_same_settings():
    """Saving the form without changes gives the same settings."""
    assert settings_from_form(form_values(SETTINGS), SETTINGS) == SETTINGS


def test_changed_form():
    """Changed inputs are read: numbers, names separated by commas (also Japanese ones), and choices."""
    values = form_values(SETTINGS)
    values.update(
        {"my_names": "A、B, C", "problems_per_game": " 3 ", "pass_ratio": "0.9", "order": "random", "rotate": True}
    )
    new = settings_from_form(values, SETTINGS)
    quiz, engine = new.quiz, new.engine
    assert quiz.extract.my_names == ("A", "B", "C")
    assert quiz.extract.problems_per_game == 3
    assert (quiz.scoring.pass_ratio, quiz.order, quiz.rotate) == (0.9, "random", True)
    assert engine == ENGINE


def test_seichi_page():
    """The settings of the territory counting practice have their own page, and their inputs are read."""
    assert "seichi" in PAGES and PAGE_GROUPS["seichi"] == ("seichi",)
    values = form_values(SETTINGS)
    assert values["seichi_order"] == "random" and values["order"] == "file_name"  # Not mixed with the quiz's.
    values.update({"seichi_order": "newest", "seichi_session_limit": "5", "seichi_review_mode": "once"})
    seichi = settings_from_form(values, SETTINGS).seichi
    assert (seichi.order, seichi.session_limit, seichi.review_mode) == ("newest", 5, "once")


def test_wrong_inputs_are_all_reported():
    """All wrong inputs are reported together, with their keys."""
    values = form_values(SETTINGS)
    values.update({"problems_per_game": "five", "tolerance": "x", "max_visits": "-1", "compare_max_visits": "x"})
    with pytest.raises(FormError) as caught:
        settings_from_form(values, SETTINGS)
    assert set(caught.value.errors) == {"problems_per_game", "tolerance", "max_visits", "compare_max_visits"}


def test_value_refused_by_the_settings():
    """A value that the settings do not allow (a pass ratio over 1) is also an error."""
    values = form_values(SETTINGS)
    values["pass_ratio"] = "80"
    with pytest.raises(FormError):
        settings_from_form(values, SETTINGS)


def test_path_exists(tmp_path):
    """A path input is fine when it is empty or names an existing file or folder of the right kind."""
    file = tmp_path / "model.bin.gz"
    file.write_text("x")
    assert path_exists("", KIND_FILE)
    assert path_exists(str(file), KIND_FILE)
    assert not path_exists(str(tmp_path / "missing"), KIND_FILE)
    assert path_exists(str(tmp_path), KIND_FOLDER)
    assert not path_exists(str(file), KIND_FOLDER)


def test_path_inside_katrain_exists(tmp_path):
    """A path that starts with "katrain/" is looked for in the KaTrain program folder, if it is known."""
    package = tmp_path / "katrain"
    (package / "models").mkdir(parents=True)
    (package / "models" / "m.bin.gz").write_text("x")
    assert path_exists("katrain/models/m.bin.gz", KIND_FILE, package)
    assert path_exists("katrain\\models\\m.bin.gz", KIND_FILE, package)  # As written on Windows.
    assert not path_exists("katrain/models/m.bin.gz", KIND_FILE)


def test_values_from_katrain(tmp_path):
    """The engine inputs are copied from KaTrain's config.json, but use_katago is kept."""
    config = tmp_path / "config.json"
    engine_config = {"katago": "/k/katago", "model": "/k/m.bin.gz", "config": "/k/a.cfg", "max_visits": 2500}
    config.write_text(json.dumps({"engine": engine_config}))
    engine = EngineSettings(katrain_config=str(config))
    values = values_from_katrain(AppSettings(QUIZ, engine))
    assert "use_katago" not in values
    assert (values["katago"], values["model"], values["max_visits"]) == ("/k/katago", "/k/m.bin.gz", "2500")


def test_values_from_missing_katrain(tmp_path):
    """When KaTrain's config.json is missing, the error tells it."""
    with pytest.raises(KataGoNotFoundError):
        values_from_katrain(AppSettings(QUIZ, EngineSettings(katrain_config=str(tmp_path / "none.json"))))


def test_needs_rereading():
    """Changing the conditions for choosing problems or the games folder makes the next start read all files."""
    assert not needs_rereading(QUIZ, QUIZ)
    assert not needs_rereading(QUIZ, replace(QUIZ, rotate=True, order="random"))
    assert needs_rereading(QUIZ, replace(QUIZ, games_folder="/other"))
    assert needs_rereading(QUIZ, replace(QUIZ, extract=ExtractSettings(my_names=("Taro",))))


def test_count_games(tmp_path):
    """Only SGF files in the folder are counted."""
    (tmp_path / "a.sgf").write_text("x")
    (tmp_path / "b.sgf").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    assert count_games(str(tmp_path)) == 2
    assert count_games(str(tmp_path / "missing")) == 0
    assert count_games("") == 0


def test_every_group_is_on_one_page():
    """Every input is on exactly one settings page."""
    groups = [group for page in PAGES for group in PAGE_GROUPS[page]]
    assert len(groups) == len(set(groups))
    assert {spec.group for spec in FIELDS} == set(groups)


def test_katrain_config_is_on_the_form():
    """The path of KaTrain's config.json can be changed, and copying from KaTrain keeps it."""
    values = form_values(SETTINGS)
    values["katrain_config"] = "/other/config.json"
    engine = settings_from_form(values, SETTINGS).engine
    assert engine.katrain_config == "/other/config.json"


def test_ai_commentary_settings_on_the_form():
    """The AI and its model are taken as they are written, so any published model can be used."""
    values = form_values(SETTINGS)
    assert (values["ai_provider"], values["ai_model"]) == ("anthropic", "claude-opus-5-5")
    assert values["model"] == SETTINGS.engine.model  # KataGo's model is another input.
    values.update({"ai_provider": "openai_compatible", "ai_model": " some-new-model ", "ai_max_tokens": "8000"})
    values["ai_base_url"] = "https://example.com/v1"
    commentary = settings_from_form(values, SETTINGS).commentary
    assert (commentary.provider, commentary.model, commentary.max_tokens) == (
        "openai_compatible",
        "some-new-model",
        8000,
    )
    assert commentary.base_url == "https://example.com/v1"


def test_decided_position_settings_on_the_form():
    """The thresholds of decided positions are quiz settings, and changing them makes the games read again."""
    values = form_values(SETTINGS)
    assert (values["decided_winrate"], values["decided_lead"]) == ("99.0", "40.0")
    values.update({"decided_winrate": "97", "decided_lead": "25"})
    new = settings_from_form(values, SETTINGS)
    assert (new.quiz.extract.decided_winrate, new.quiz.extract.decided_lead) == (97.0, 25.0)
    assert needs_rereading(SETTINGS.quiz, new.quiz)


def test_wrong_decided_winrate():
    """A winrate below 50 % or above 100 % is not allowed."""
    values = form_values(SETTINGS)
    values["decided_winrate"] = "120"
    with pytest.raises(FormError):
        settings_from_form(values, SETTINGS)
