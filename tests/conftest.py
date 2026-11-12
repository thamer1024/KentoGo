"""Settings shared by all tests."""

import pytest

from kentogo import analysis_timing
from kentogo.gui.texts import DEFAULT_LANGUAGE, set_language


@pytest.fixture(autouse=True)
def timing_log_in_tmp(tmp_path, monkeypatch):
    """The analysis timing log is written in the test's own folder, never in the user's ~/.kentogo."""
    monkeypatch.setattr(analysis_timing, "LOG_PATH", tmp_path / "analysis_timing.jsonl")


@pytest.fixture(autouse=True)
def japanese_texts():
    """Most tests check the messages in Japanese (the source of the translations).

    The tests of the languages (gui/test_languages.py) choose their languages themselves.
    """
    set_language("jp")
    yield
    set_language(DEFAULT_LANGUAGE)
