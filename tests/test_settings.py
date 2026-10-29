"""Tests for kentogo.settings."""

import json

import pytest

from kentogo.settings import SettingsStore

DEFAULTS = {"quiz": {"problems_per_game": 5, "my_names": []}, "engine": {"visits": 500}}


def test_defaults_when_there_is_no_file(tmp_path):
    """Without a file, the default values are used."""
    store = SettingsStore(tmp_path / "settings.json", DEFAULTS)
    store.load()
    assert store.section("quiz") == {"problems_per_game": 5, "my_names": []}


def test_file_values_replace_defaults(tmp_path):
    """Values in the file replace the defaults, and missing keys keep their default values."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"quiz": {"problems_per_game": 3}, "other": {"x": 1}}), encoding="utf-8")
    store = SettingsStore(path, DEFAULTS)
    store.load()
    assert store.section("quiz") == {"problems_per_game": 3, "my_names": []}
    assert store.section("engine") == {"visits": 500}
    assert store.section("other") == {"x": 1}


def test_save_and_load_again(tmp_path):
    """Saved values are read back, including non-ASCII text."""
    path = tmp_path / "folder" / "settings.json"
    store = SettingsStore(path, DEFAULTS)
    store.set_section("quiz", {"problems_per_game": 7, "my_names": ["太郎"]})
    store.save()
    assert "太郎" in path.read_text(encoding="utf-8")

    again = SettingsStore(path, DEFAULTS)
    again.load()
    assert again.section("quiz") == {"problems_per_game": 7, "my_names": ["太郎"]}
    assert list(path.parent.iterdir()) == [path]  # No temporary file is left.


def test_section_is_a_copy(tmp_path):
    """Changing a returned section does not change the store or the defaults."""
    store = SettingsStore(tmp_path / "settings.json", DEFAULTS)
    store.section("quiz")["my_names"].append("x")
    assert store.section("quiz")["my_names"] == []
    assert DEFAULTS["quiz"]["my_names"] == []


@pytest.mark.parametrize("text", ["{broken", "[1, 2]", '{"quiz": 5}'])
def test_broken_file(tmp_path, text):
    """A broken file is an error, so that the user's settings are not silently lost."""
    path = tmp_path / "settings.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        SettingsStore(path, DEFAULTS).load()
