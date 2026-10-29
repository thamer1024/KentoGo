"""Tests for the languages of kentogo.gui.texts: the files in kentogo/locales, and switching."""

import json
import re
import string

import pytest

from kentogo.gui import texts
from kentogo.gui.texts import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    LOCALES_FOLDER,
    SOURCE_LANGUAGE,
    TEXTS,
    gap,
    language,
    lazy,
    list_text,
    load_texts,
    set_language,
    text,
)
from kentogo.gui.theme import flag_image

MARKUP = re.compile(r"\[/?[a-z]+(?:=[^\]]*)?\]")
TRANSLATED = [code for code in LANGUAGES if code != SOURCE_LANGUAGE]


@pytest.fixture(autouse=True)
def back_to_the_default_language():
    """Every test starts in English, and the language is set back to English after it."""
    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(DEFAULT_LANGUAGE)


def _placeholders(value: str) -> list[str]:
    """Return the {values} of a text, with their formats, such as "actual:.1f"."""
    return sorted(
        f"{name}:{spec}" if spec else name for _, name, spec, _ in string.Formatter().parse(value) if name is not None
    )


@pytest.mark.parametrize("code", TRANSLATED)
def test_every_language_file_matches_the_japanese_texts(code):
    """Each file has the same keys as TEXTS, every text is filled, and has the same {values} and markup."""
    own = json.loads((LOCALES_FOLDER / f"{code}.json").read_text(encoding="utf-8"))
    assert set(own) == set(TEXTS)
    for key, value in own.items():
        assert value, f"{code}: {key} is empty"
        assert _placeholders(value) == _placeholders(TEXTS[key]), f"{code}: {key}"
        assert sorted(MARKUP.findall(value)) == sorted(MARKUP.findall(TEXTS[key])), f"{code}: {key}"


def test_english_is_used_until_another_language_is_chosen():
    """The default language is English; Japanese gives the texts of TEXTS."""
    assert language() == "en" and text("black") == "Black"
    set_language("jp")
    assert language() == "jp" and text("black") == TEXTS["black"]


def test_lazy_texts_follow_the_language():
    """A lazy text is made in the language used when it is called."""
    make = lazy("lead_black", points="3")
    english = make()
    set_language("de")
    assert make() != english and "3" in make()


def test_missing_texts_are_shown_in_english(tmp_path, monkeypatch):
    """A text that a language does not have yet is shown in English."""
    english = json.loads((LOCALES_FOLDER / "en.json").read_text(encoding="utf-8"))
    german = json.loads((LOCALES_FOLDER / "de.json").read_text(encoding="utf-8"))
    del german["black"]
    (tmp_path / "en.json").write_text(json.dumps(english), encoding="utf-8")
    (tmp_path / "de.json").write_text(json.dumps(german), encoding="utf-8")
    monkeypatch.setattr(texts, "LOCALES_FOLDER", tmp_path)
    assert load_texts("de")["black"] == "Black"


def test_unknown_language():
    """A language that KentoGo does not have is an error, and the language does not change."""
    with pytest.raises(ValueError):
        set_language("xx")
    assert language() == DEFAULT_LANGUAGE


def test_lists_and_gaps_follow_the_language():
    """Japanese and Chinese join lists with "、" and use a full-width space; the others do not."""
    assert list_text(["a", "b"]) == "a, b" and gap() == "  "
    set_language("jp")
    assert list_text(["a", "b"]) == "a、b" and gap() == "　"


def test_every_language_has_a_flag():
    """The flag image of each language is in the package (English has the UK flag, as in KaTrain)."""
    for code in LANGUAGES:
        assert flag_image(code).is_file()
    assert flag_image("en").name == "flag-uk.png"
