"""The texts shown on the screens, in the chosen language.

TEXTS (see gui.source_texts) holds the Japanese texts, which are the source of the translations. The
other languages are in kentogo/locales/<language>.json, with the same {values}
(see LANGUAGES; the codes are KaTrain's). English has every text; a new text is
written in Japanese and English only, and the other languages get it when they
are translated. English is used until another language is chosen; a text missing
from a language is shown in English.

The texts of each practice are put together in its own module (see gui.quiz_texts, gui.report_texts, ...).

The texts use Kivy markup, such as [b]...[/b] and [color=...]...[/color].
Colored texts use light colors, so that they are easy to read on the dark
background of the panel (contrast ratio of about 4.5 or more).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from kentogo.gui.source_texts import TEXTS
from kentogo.notice import Notice

# The languages, in the order of their flags (KaTrain's order, with Spanish after Ukrainian).
LANGUAGES = ("en", "de", "fr", "ua", "es", "ru", "cn", "tw", "ko", "jp", "tr")
DEFAULT_LANGUAGE = "en"
SOURCE_LANGUAGE = "jp"  # The language of TEXTS.
LOCALES_FOLDER = Path(__file__).resolve().parent.parent / "locales"
# Languages that write lists with "、" and put a full-width space between parts of a line.
_CJK_PUNCTUATION = ("jp", "cn", "tw")


def load_texts(language: str) -> dict[str, str]:
    """Return all texts of a language. Texts that the language does not have are in English.

    Args:
        language: One of LANGUAGES.

    Raises:
        ValueError: If the language is not one of LANGUAGES.
        OSError: If the file of the language cannot be read.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unknown language: {language}")
    if language == SOURCE_LANGUAGE:
        return dict(TEXTS)
    english = _read_locale(DEFAULT_LANGUAGE)
    own = _read_locale(language) if language != DEFAULT_LANGUAGE else english
    # Japanese is the last fallback, so that a key added to TEXTS but not yet translated still works.
    return {key: own.get(key) or english.get(key) or value for key, value in TEXTS.items()}


def _read_locale(language: str) -> dict[str, str]:
    """Read the texts of one language from its file in LOCALES_FOLDER."""
    path = LOCALES_FOLDER / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))


_language = DEFAULT_LANGUAGE
_texts = load_texts(DEFAULT_LANGUAGE)


def set_language(language: str) -> None:
    """Use another language for all texts from now on.

    Widgets that already show texts are not changed here (see gui.widgets.relabel_all).

    Raises:
        ValueError: If the language is not one of LANGUAGES.
        OSError: If the file of the language cannot be read.
    """
    global _language, _texts
    _texts = load_texts(language)
    _language = language


def language() -> str:
    """Return the language that is used now."""
    return _language


def text(key: str, **values) -> str:
    """Return the text for a key in the language used now, with the values filled in."""
    return _texts[key].format(**values)


def template(key: str) -> str:
    """Return the text for a key in the language used now, with its {values} not filled in."""
    return _texts[key]


def notice_text(notice: Notice | None) -> str:
    """Return a message given by a part without screens (see kentogo.notice) in words, or "" for None."""
    return text(notice.key, **notice.values) if notice is not None else ""


def notices_text(notices) -> str:
    """Return several messages (see notice_text), with an empty line between them."""
    return "\n\n".join(notice_text(notice) for notice in notices)


def lazy(key: str, **values) -> Callable[[], str]:
    """Return a function that makes the text, so that it can be made again in another language."""
    return lambda: text(key, **values)


def list_text(items: list[str]) -> str:
    """Join the parts of a list in the way of the language ("A、B" or "A, B")."""
    return ("、" if _language in _CJK_PUNCTUATION else ", ").join(items)


def gap() -> str:
    """Return the space between two parts of a line (a full-width space in Japanese and Chinese)."""
    return "　" if _language in _CJK_PUNCTUATION else "  "


def color_name(color: str) -> str:
    """Return the name of a color ("B" or "W")."""
    return text("black") if color == "B" else text("white")
