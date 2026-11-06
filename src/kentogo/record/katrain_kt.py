"""Read and write KaTrain's analysis data (the KT property), to know the loss of each candidate move.

When KaTrain's "Save analysis in SGF" is on, each analyzed node has a KT
property. It has three texts, each gzip-compressed and then base64-encoded:
the ownership and the policy (packed numbers, not used here), and the main
analysis as JSON (KaTrain 1.20.0, katrain/core/game_node.py, analysis_dumps).
encode_kt writes the KT property with KaTrain's own code, copied unchanged into vendor.katrain_analysis,
so KaTrain can read the games that KentoGo analyzes.

The main analysis of a node is about the position after that node: "root" has
the score of the position, and "moves" has, for each candidate next move (by
its GTP point), the score after it. Scores are from black's point of view, so
the loss of a move is (root score - move score) for black and the opposite for
white, as in KaTrain's GameNode.candidate_moves.

The loss of the move that was played is the score before it (the analysis of the node before)
minus the score after it (the analysis of its own node), as in KaTrain's GameNode.points_lost.
This data does not depend on KaTrain's language or wording, so it is read before the comments
(see mistakes.extract).
"""

from __future__ import annotations

import base64
import gzip
import json
import struct
from dataclasses import dataclass

from kentogo.vendor.katrain_analysis import analysis_dumps, unpack_floats

# The newest version of the format that this module can read (KaTrain's ANALYSIS_FORMAT_VERSION).
SUPPORTED_VERSION = "1.0"

# Games analyzed in KentoGo's own mode (see analysis.rules) have KGM[KentoGo] at the root. Their
# losses are read in the position before each move, from the best move (see played_move_loss).
KENTOGO_MODE_PROPERTY = "KGM"
KENTOGO_MODE = "KentoGo"

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


def encode_kt(analysis: dict) -> list[str]:
    """Return the texts of the KT property of a node, written by KaTrain's own code (vendor.katrain_analysis).

    Args:
        analysis: The analysis of the node, as KaTrain keeps it: "moves" (each candidate move by its
            GTP point), "root", "ownership" and "policy" (lists of numbers, or None) and "completed".

    Returns:
        Three texts: the ownership, the policy, and the rest of the analysis as JSON.
    """
    return analysis_dumps({"ownership": None, "policy": None, **analysis})


def decode_kt_numbers(values: list[str], board_points: int) -> tuple[tuple[float, ...] | None, ...]:
    """Return the ownership and the policy of a node from the texts of its KT property.

    The numbers are unpacked by KaTrain's own code (vendor.katrain_analysis), as KaTrain's load_analysis does.

    Args:
        values: The texts of the KT property.
        board_points: The number of points of the board (361 for 19x19); the policy has one more, for passing.

    Returns:
        The ownership and the policy, each None when it was not saved.

    Raises:
        ValueError: If the data is broken.
    """
    if len(values) < 2:
        raise ValueError(f"KaTrain's analysis data has {len(values)} parts, not 3")
    try:
        ownership, policy = (gzip.decompress(base64.standard_b64decode(value)) for value in values[:2])
        return unpack_floats(ownership, board_points), unpack_floats(policy, board_points + 1)
    except (ValueError, OSError, EOFError, struct.error) as error:
        raise ValueError(f"broken KaTrain analysis data: {error}") from error


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


def relative_candidate_losses(analysis: dict, color: str) -> dict[str, float]:
    """Return the loss of each candidate move from the best one (KaTrain's relativePointsLost), never below 0.

    KentoGo's mode uses it: the best candidate (KataGo's order 0) loses exactly 0, and the others
    lose what they give up against it. Without a ranked candidate, the root's score is the reference.
    """
    root = analysis.get("root") or {}
    moves = analysis.get("moves") or {}
    if not isinstance(root, dict) or "scoreLead" not in root or not isinstance(moves, dict):
        return {}
    reference = _best_score(analysis)
    sign = _SIGNS[color]
    return {
        point.upper(): max(0.0, sign * (reference - values["scoreLead"]))
        for point, values in moves.items()
        if isinstance(values, dict) and isinstance(values.get("scoreLead"), int | float)
    }


def played_move_loss(before: dict, color: str, move_gtp: str) -> float | None:
    """Return the points lost by a played move from the best move, read in the position before it (KentoGo's mode).

    The value can be below 0 when the played move, read as deeply as the position, turned out better
    than KataGo's first choice. None when the position before has no value for the played move.
    """
    played = (before.get("moves") or {}).get(move_gtp)
    if not isinstance(played, dict) or _number(played.get("scoreLead")) is None or root_value(before)[1] is None:
        return None
    return _SIGNS[color] * (_best_score(before) - played["scoreLead"])


def evaluate_played_move(before: dict, after: dict, color: str, move_gtp: str) -> KtEvaluation | None:
    """Return the evaluation of a move of a game analyzed in KentoGo's mode (see played_move_loss).

    The loss is never below 0 here: a move better than KataGo's first choice lost nothing. Without
    the played move's value in the position before it, the move is evaluated as KaTrain does it.
    """
    loss = played_move_loss(before, color, move_gtp)
    evaluation = evaluate_move(before, after, color)
    if loss is None or evaluation is None:
        return evaluation
    return KtEvaluation(round(max(0.0, loss), 2), evaluation.best_move, evaluation.pv)


def evaluate_katrain_move(before: dict, after: dict, color: str, move_gtp: str) -> KtEvaluation | None:
    """Return the evaluation of a move as KaTrain does it (see evaluate_move); move_gtp is not needed."""
    return evaluate_move(before, after, color)


def _best_score(analysis: dict) -> float:
    """Return the score of the best candidate (KataGo's order 0), or the root's score without one."""
    best = _best_candidate(analysis)
    if best is not None and _number(best[1].get("scoreLead")) is not None and best[1].get("order") == 0:
        return float(best[1]["scoreLead"])
    return float(analysis["root"]["scoreLead"])


@dataclass(frozen=True)
class KtEvaluation:
    """The evaluation of a played move, from the analysis data of the node before it and of its own node.

    Attributes:
        points_lost: Points lost by the move, for its player (never below 0).
        best_move: The best candidate move in the position before the move (GTP, such as "Q16"),
            or None if the analysis does not rank its candidates.
        pv: KataGo's predicted sequence from that position, starting with the best move (GTP), or ().
    """

    points_lost: float
    best_move: str | None
    pv: tuple[str, ...]


def evaluate_move(before: dict, after: dict, color: str) -> KtEvaluation | None:
    """Return the evaluation of a move from the analyses of the node before it and of its own node.

    Args:
        before: The main analysis of the node before the move (see decode_kt).
        after: The main analysis of the node of the move.
        color: The player of the move, "B" or "W".

    Returns:
        The evaluation, or None if either analysis has no root score.
    """
    lead_before, lead_after = root_value(before)[1], root_value(after)[1]
    if lead_before is None or lead_after is None:
        return None
    points_lost = round(max(0.0, _SIGNS[color] * (lead_before - lead_after)), 2)
    best = _best_candidate(before)
    if best is None:
        return KtEvaluation(points_lost, None, ())
    point, values = best
    pv = tuple(str(move).upper() for move in values.get("pv") or () if isinstance(move, str))
    return KtEvaluation(points_lost, point.upper(), pv)


def _best_candidate(analysis: dict) -> tuple[str, dict] | None:
    """Return the candidate move ranked first (the smallest "order"), with its values, or None."""
    moves = analysis.get("moves") or {}
    if not isinstance(moves, dict):
        return None
    ranked = [
        (values["order"], point, values)
        for point, values in moves.items()
        if isinstance(values, dict) and isinstance(values.get("order"), int)
    ]
    if not ranked:
        return None
    _, point, values = min(ranked, key=lambda item: item[0])
    return point, values


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
