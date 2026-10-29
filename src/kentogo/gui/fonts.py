"""The fonts for the screens, one for each language.

Kivy's default font cannot show Japanese, Chinese or Korean, and Kivy uses one
font for a text (no fallback font). So each language gets a font that has all
of its characters, as in KaTrain:
- Japanese, and the languages written with Latin or Cyrillic letters that it covers:
  Noto Sans JP (the same font as KaTrain).
- Chinese and Korean: Noto Sans CJK SC (the same font as KaTrain).
- Turkish and Ukrainian: DejaVu Sans. KaTrain uses Noto Sans for them, but it does
  not have the marks used on KentoGo's screens, such as "△", "☆" and "▶".
The Noto fonts are under the SIL Open Font License (see fonts/OFL.txt), and DejaVu
Sans under its own license (see fonts/DejaVu-LICENSE.txt).
"""

from __future__ import annotations

from pathlib import Path

FONTS_FOLDER = Path(__file__).resolve().parent.parent / "fonts"
JAPANESE_FONT = "NotoSansJP-Regular.otf"
CJK_FONT = "NotoSansCJKsc-Regular.otf"
LATIN_FONT = "DejaVuSans.ttf"
# The fonts of the languages that do not use JAPANESE_FONT.
LANGUAGE_FONTS = {"cn": CJK_FONT, "tw": CJK_FONT, "ko": CJK_FONT, "tr": LATIN_FONT, "ua": LATIN_FONT}

# The name of Kivy's default font. Every Label uses it unless another font is given.
KIVY_DEFAULT_FONT_NAME = "Roboto"


def font_path(language: str) -> Path:
    """Return the path of the font for a language (one of texts.LANGUAGES)."""
    return FONTS_FOLDER / LANGUAGE_FONTS.get(language, JAPANESE_FONT)


def register_font(language: str) -> None:
    """Make the font of a language the default font of all text in Kivy.

    The font is registered under the name of Kivy's default font, so every Label
    uses it without setting font_name. Call this before the first screen is made,
    and again when the language is changed (texts made after that use the new font).
    """
    from kivy.core.text import LabelBase

    LabelBase.register(KIVY_DEFAULT_FONT_NAME, str(font_path(language)))
