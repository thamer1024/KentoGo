"""Read KaTrain's analysis data (the KT property) to know the loss of each candidate move.

When KaTrain's "Save analysis in SGF" is on, each analyzed node has a KT
property. It has three texts, each gzip-compressed and then base64-encoded:
the ownership and the policy (packed numbers, not used here), and the main
analysis as JSON (KaTrain 1.20.0, katrain/core/game_node.py, analysis_dumps).

The main analysis of a node is about the position after that node: "root" has
the score of the position, and "moves" has, for each candidate next move (by
its GTP point), the score after it. Scores are from black's point of view, so
the loss of a move is (root score - move score) for black and the opposite for
white, as in KaTrain's GameNode.candidate_moves.
"""

from __future__ import annotations

import base64
import gzip
import json

# The newest version of the format that this module can read (KaTrain's ANALYSIS_FORMAT_VERSION).
SUPPORTED_VERSION = "1.0"

# The color that a loss is counted for: black's score up is good for black.
_SIGNS = {"B": 1, "W": -1}


def decode_kt(values: list[str], version: str = SUPPORTED_VERSION) -> dict:
    """Return the main analysis of a node from the texts of its KT property.

    Args:
        values: The texts of the KT property (three for KaTrain 1.20.0).
        version: The KTV property of the root node (the version of the format).

    Returns:
        The main analysis, with "root" and "moves".

    Raises:
        ValueError: If the version is newer than this module can read, or the data is broken.
    """
    if _version_number(version) > _version_number(SUPPORTED_VERSION):
        raise ValueError(f"KaTrain's analysis data version {version} is newer than {SUPPORTED_VERSION}")
    if len(values) < 3:
        raise ValueError(f"KaTrain's analysis data has {len(values)} parts, not 3")
    try:
        analysis = json.loads(gzip.decompress(base64.standard_b64decode(values[2])))
    except (ValueError, OSError, EOFError) as error:
        raise ValueError(f"broken KaTrain analysis data: {error}") from error
    if not isinstance(analysis, dict):
        raise ValueError("broken KaTrain analysis data: not a JSON object")
    return analysis


def candidate_losses(analysis: dict, color: str) -> dict[str, float]:
    """Return the loss of each candidate move in an analysis, for the player who moves next.

    Args:
        analysis: The main analysis of the node before the move (see decode_kt).
        color: The player who moves next, "B" or "W".

    Returns:
        A dict from GTP point (such as "Q16" or "pass") to the points lost, never below 0.
        It is empty if the analysis has no root score or no moves.
    """
    root = analysis.get("root") or {}
    moves = analysis.get("moves") or {}
    if not isinstance(root, dict) or "scoreLead" not in root or not isinstance(moves, dict):
        return {}
    sign = _SIGNS[color]
    losses = {}
    for point, values in moves.items():
        if isinstance(values, dict) and isinstance(values.get("scoreLead"), int | float):
            losses[point.upper()] = max(0.0, sign * (root["scoreLead"] - values["scoreLead"]))
    return losses


def root_value(analysis: dict) -> tuple[float | None, float | None]:
    """Return black's winrate (0 to 1) and black's score lead of the position of an analysis (None if not there)."""
    root = analysis.get("root") or {}
    if not isinstance(root, dict):
        return None, None
    return _number(root.get("winrate")), _number(root.get("scoreLead"))


def _number(value: object) -> float | None:
    """Return a value of the analysis as a float, or None if it is not a number."""
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _version_number(version: str) -> tuple[int, ...]:
    """Turn a version such as "1.0" into numbers that can be compared. A wrong text counts as very new."""
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError:
        return (999,)
