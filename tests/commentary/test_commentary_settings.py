"""Tests for kentogo.commentary.commentary_settings, and the "commentary" part of the settings file."""

import pytest

from kentogo.app_settings import AppSettings
from kentogo.commentary.commentary_settings import PROVIDER_OPENAI_COMPATIBLE, CommentarySettings


def test_defaults_and_round_trip():
    """The defaults are the user's script's (Claude Opus 5.5), and the settings survive the settings file."""
    settings = CommentarySettings()
    assert (settings.provider, settings.model, settings.api_key_env) == (
        "anthropic",
        "claude-opus-5-5",
        "ANTHROPIC_API_KEY",
    )
    changed = CommentarySettings(PROVIDER_OPENAI_COMPATIBLE, "gpt-x", "http://localhost:11434/v1", "OPENAI_API_KEY")
    assert CommentarySettings.from_dict(changed.to_dict()) == changed
    assert AppSettings.from_sections(AppSettings(commentary=changed).sections()).commentary == changed


def test_missing_and_unknown_keys():
    """Missing keys get the defaults, and unknown keys (such as prices kept by an earlier version) are ignored."""
    settings = CommentarySettings.from_dict({"model": "m", "input_price": 3, "other": 1})
    assert (settings.model, settings.max_tokens) == ("m", 15000)


@pytest.mark.parametrize(
    "values",
    [{"provider": "other"}, {"model": 5}, {"max_tokens": 0}, {"max_tokens": "many"}],
)
def test_wrong_values(values):
    """Wrong values are errors."""
    with pytest.raises(ValueError):
        CommentarySettings.from_dict(values)
