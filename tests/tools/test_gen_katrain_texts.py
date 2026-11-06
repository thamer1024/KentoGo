"""Tests for tools/gen_katrain_texts.py (the table of KaTrain texts)."""

import importlib.util
from pathlib import Path

TOOL = Path(__file__).parents[2] / "tools" / "gen_katrain_texts.py"
spec = importlib.util.spec_from_file_location("gen_katrain_texts", TOOL)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def texts(**changed: str) -> dict[str, str]:
    """Return the texts of a language, each one its own key with " text" after it, with some changed."""
    return {key: changed.get(key.replace(":", "_").replace(" ", "_"), f"{key} text") for key in gen.KEYS}


def test_the_written_module_is_read_back(tmp_path):
    """A table written by build_module is read back the same."""
    table = {"en": texts(), "jp": texts(move="手数 {number}")}
    path = tmp_path / "katrain_texts.py"
    path.write_text(gen.build_module(table, "9.9.9"), encoding="utf-8")
    assert gen.load_table(path) == table
    assert gen.load_table(tmp_path / "missing.py") == {}


def test_differences():
    """Added and removed languages, and changed texts, are each told on a line."""
    old = {"en": texts(), "de": texts()}
    new = {"en": texts(Info_PV="Variation: {pv}"), "fr": texts()}
    assert gen.differences(old, new) == [
        "new language: fr",
        "language removed: de",
        "en Info:PV: 'Info:PV text' -> 'Variation: {pv}'",
    ]
    assert gen.differences(old, old) == []


def test_missing_keys():
    """A text that is its own message ID in the default language is missing in KaTrain."""
    assert gen.missing_keys({"en": texts(move="move")}, "en") == ["move"]
    assert gen.missing_keys({"en": texts()}, "en") == []
