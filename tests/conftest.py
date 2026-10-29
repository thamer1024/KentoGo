"""Settings shared by all tests."""

import pytest

from kentogo.gui.texts import DEFAULT_LANGUAGE, set_language


@pytest.fixture(autouse=True)
def japanese_texts():
    """Most tests check the messages in Japanese (the source of the translations).

    The tests of the languages (gui/test_languages.py) choose their languages themselves.
    """
    set_language("jp")
    yield
    set_language(DEFAULT_LANGUAGE)
