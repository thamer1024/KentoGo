"""Rule sets, read in the same way as KaTrain.

KaTrain lets the user choose one of the rule sets in RULESETS, and writes the
name to the RU property of the SGF file. Files from other programs can use
other spellings (such as "Chinese" or "cn"), and KaTrain also accepts a JSON
text with KataGo's rule settings.

For playing moves on the board, the rule sets differ only in suicide:
KaTrain allows a suicide of two or more stones under Tromp-Taylor and
New Zealand rules (or when a JSON rule says "suicide": true).
A suicide of a single stone is never allowed.
"""

from __future__ import annotations

import json

DEFAULT_RULES = "japanese"

# (short name, full name) of the rule sets that KaTrain can use (KaTrain 1.20.0).
RULESETS_ABBR = [
    ("jp", "japanese"),
    ("cn", "chinese"),
    ("ko", "korean"),
    ("aga", "aga"),
    ("tt", "tromp-taylor"),
    ("nz", "new zealand"),
    ("stone_scoring", "stone_scoring"),
]

# A dict from short name or full name to full name.
RULESETS = {key: name for abbr, name in RULESETS_ABBR for key in (abbr, name)}

# The rule sets that allow a suicide of two or more stones.
_SUICIDE_RULESETS = {"tromp-taylor", "new zealand"}


def normalize_rules(text: str | None) -> str | dict:
    """Read the RU property in the same way as KaTrain.

    Args:
        text: The RU property, or None if the file does not have it.

    Returns:
        The full name of the rule set (such as "chinese"), or a dict when the
        text is a JSON object with KataGo's rule settings. Unknown names
        become DEFAULT_RULES, as in KaTrain.
    """
    if text is None:
        return DEFAULT_RULES
    if text.strip().startswith("{"):
        try:
            rules = json.loads(text)
        except json.JSONDecodeError:
            rules = None
        if isinstance(rules, dict):
            return rules
    return RULESETS.get(text.strip().lower(), DEFAULT_RULES)


def allows_suicide(rules: str | dict) -> bool:
    """Return True if the rules allow a suicide of two or more stones.

    Args:
        rules: A value returned by normalize_rules.
    """
    if isinstance(rules, dict):
        return bool(rules.get("suicide", False))
    return rules in _SUICIDE_RULESETS
