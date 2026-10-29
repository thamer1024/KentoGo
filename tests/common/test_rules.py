"""Tests for kentogo.common.rules."""

import pytest

from kentogo.common.rules import DEFAULT_RULES, RULESETS_ABBR, allows_suicide, normalize_rules


@pytest.mark.parametrize(("abbr", "name"), RULESETS_ABBR)
def test_names_of_katrain_rulesets(abbr, name):
    """Both the short name and the full name give the full name, in any case."""
    assert normalize_rules(abbr) == name
    assert normalize_rules(name.upper()) == name


def test_unknown_or_missing_rules():
    """Unknown names and a missing RU property become the default rules, as in KaTrain."""
    assert normalize_rules("something else") == DEFAULT_RULES
    assert normalize_rules(None) == DEFAULT_RULES


def test_json_rules():
    """A JSON object is read as KataGo's rule settings."""
    assert normalize_rules('{"ko": "POSITIONAL", "suicide": true}') == {"ko": "POSITIONAL", "suicide": True}
    assert normalize_rules("{not json") == DEFAULT_RULES


def test_allows_suicide():
    """Only Tromp-Taylor, New Zealand, and JSON rules with "suicide": true allow suicide."""
    allowed = {name for _, name in RULESETS_ABBR if allows_suicide(name)}
    assert allowed == {"tromp-taylor", "new zealand"}
    assert allows_suicide({"suicide": True})
    assert not allows_suicide({"ko": "SIMPLE"})
