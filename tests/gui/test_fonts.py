"""Tests for kentogo.gui.fonts."""

import pytest

from kentogo.gui.fonts import FONTS_FOLDER, font_path
from kentogo.gui.texts import LANGUAGES, load_texts


def test_fonts_and_licenses_are_included():
    """The font of every language and the licenses of the fonts are in the package."""
    for language in LANGUAGES:
        assert font_path(language).is_file()
    assert (FONTS_FOLDER / "OFL.txt").is_file()
    assert (FONTS_FOLDER / "DejaVu-LICENSE.txt").is_file()


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_font_has_every_character_of_the_language(language):
    """Kivy has no fallback font, so the font of a language must have all characters of its texts."""
    ttlib = pytest.importorskip("fontTools.ttLib")
    characters = set(ttlib.TTFont(font_path(language), fontNumber=0).getBestCmap())
    shown = "".join(load_texts(language).values()).replace("\n", "")
    missing = sorted({character for character in shown if ord(character) not in characters})
    assert missing == []
