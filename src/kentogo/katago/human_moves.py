"""The move that a human of a rank would most likely play, from KataGo's human-like model.

KaTrain's human-like AI asks KataGo with the human-like model (KataGo started with -human-model) for
"humanPolicy" with a profile such as "rank_10k" (KaTrain 1.20.0, HumanStyleStrategy.generate_move,
which then chooses a move at random by these chances). Here the move with the biggest chance is taken,
so that the same position always gives the same move. The policy needs no search: one visit is read.

A natural and strong move of a human-like player is also chosen here: the candidates are the moves that the
human may play (see candidate_moves), KataGo reads only them (see restricted_query), and the move with the least
loss is played; among the moves whose losses are about the same (LOSS_TOLERANCE), the most likely one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from kentogo.common.types import GTP_COLUMNS, Move, Position
from kentogo.katago.queries import position_query

HUMAN_VISITS = 1  # The human-like policy is that of the position itself.
NATURAL_RATIO = 0.05  # A move is natural for the human if its chance is at least this part of the likeliest move's ...
MAX_CANDIDATES = 12  # ... (and the candidates are at most this many moves).
# Moves whose losses differ by this many points or less are equally good (the reading is not exact).
LOSS_TOLERANCE = 0.3
# The ranks of KataGo's human-like model: 20k to 1k, and 1d to 9d.
_RANK = re.compile(r"(?:(?:[1-9]|1[0-9]|20)k|[1-9]d)")


def human_profile(rank: str) -> str:
    """Return KataGo's humanSLProfile of a rank such as "10k" or "1d": "rank_10k" ("" if it is not such a rank)."""
    return f"rank_{rank}" if _RANK.fullmatch(rank) else ""


def human_query(position: Position, extra_moves: tuple[Move, ...], profile: str) -> dict:
    """Make a query for the human-like policy of a position after some moves (see human_profile)."""
    query = position_query(position, extra_moves, HUMAN_VISITS)
    query["includePolicy"] = True
    # The same settings as KaTrain's human-like AI.
    query["overrideSettings"] = {**query["overrideSettings"], "humanSLProfile": profile, "ignorePreRootHistory": False}
    return query


def most_likely_move(answer: dict, size: int, color: str) -> Move:
    """Return the move with the biggest chance in the human-like policy of KataGo's answer.

    KataGo's policy goes row by row from the top row, and its last value is the pass.

    Raises:
        ValueError: If the answer is an error, or has no human-like policy (KataGo has no human-like model).
    """
    policy = _human_policy(answer, size)
    return _move_at(max(range(len(policy)), key=lambda point: policy[point]), size, color)


def most_likely_among(answer: dict, size: int, color: str, points: list[str]) -> Move:
    """Return the move among the points (GTP) with the biggest chance in the human-like policy.

    Raises:
        ValueError: If the answer is an error, or has no human-like policy (KataGo has no human-like model).
    """
    policy = _human_policy(answer, size)
    moves = [Move.from_gtp(point, color) for point in points]
    return max(moves, key=lambda move: policy[(size - 1 - move.coord[1]) * size + move.coord[0]])


@dataclass(frozen=True)
class Candidate:
    """A move that a human of the profile may play.

    Attributes:
        move: The move.
        chance: Its chance in the human-like policy.
    """

    move: Move
    chance: float


def candidate_moves(answer: dict, size: int, color: str) -> tuple[Candidate, ...]:
    """Return the moves that a human of the profile may play, from the most likely one (see NATURAL_RATIO).

    A move is a candidate if its chance is at least NATURAL_RATIO of the likeliest move's (at most MAX_CANDIDATES
    moves). A pass is not a candidate, unless it is the most likely move (then it is the only one).

    Raises:
        ValueError: If the answer is an error, or has no human-like policy (KataGo has no human-like model).
    """
    policy = _human_policy(answer, size)
    ranked = sorted(range(len(policy)), key=lambda point: policy[point], reverse=True)
    if ranked[0] == size * size:
        return (Candidate(_move_at(ranked[0], size, color), policy[ranked[0]]),)
    floor = NATURAL_RATIO * policy[ranked[0]]
    chosen = [index for index in ranked if index != size * size and policy[index] >= floor]
    return tuple(Candidate(_move_at(index, size, color), policy[index]) for index in chosen[:MAX_CANDIDATES])


def choose_natural(candidates: tuple[Candidate, ...], losses: Mapping[str, float]) -> Candidate | None:
    """Return the candidate with the least loss; among those within LOSS_TOLERANCE of it, the most likely one.

    A candidate whose loss is not known (not in losses) is not chosen. None if no candidate has a known loss.

    Args:
        candidates: The candidates, from the most likely one.
        losses: The points lost by a move, by its GTP point (against the best move).
    """
    known = [(candidate, losses[candidate.move.gtp()]) for candidate in candidates if candidate.move.gtp() in losses]
    if not known:
        return None
    least = min(loss for _, loss in known)
    return next(candidate for candidate, loss in known if loss <= least + LOSS_TOLERANCE)


def move_scores(answer: dict) -> dict[str, float]:
    """Return the score lead after each move that KataGo read, from black's side, by its GTP point.

    Raises:
        ValueError: If the answer is an error.
    """
    if "error" in answer:
        raise ValueError(f"KataGo could not analyze the position: {answer['error']}")
    return {info["move"]: float(info["scoreLead"]) for info in answer.get("moveInfos") or [] if "scoreLead" in info}


def losses_of(scores: Mapping[str, float], color: str) -> dict[str, float]:
    """Return the points lost by each move of scores (from black's side) against the best of them."""
    if not scores:
        return {}
    sign = 1 if color == "B" else -1  # The scores are from black's side.
    best = max(sign * score for score in scores.values())
    return {move: best - sign * score for move, score in scores.items()}


def restricted_query(
    position: Position,
    extra_moves: tuple[Move, ...],
    candidates: tuple[Move, ...],
    visits: int,
    max_time: float = 0.0,
) -> dict:
    """Make a query for KataGo's own search that plays only the candidate moves (KataGo's "allowMoves").

    The human-like profile is not used in this search, and no noise is added to the root (the few visits are
    to tell the candidates apart, not to find new moves).
    """
    query = position_query(position, extra_moves, visits, max_time=max_time)
    allowed = {"player": candidates[0].color, "moves": [move.gtp() for move in candidates], "untilDepth": 1}
    query["allowMoves"] = [allowed]
    return query


def _human_policy(answer: dict, size: int) -> list[float]:
    """Return the human-like policy of KataGo's answer (row by row from the top row; the last value is the pass).

    Raises:
        ValueError: If the answer is an error, or has no human-like policy (KataGo has no human-like model).
    """
    if "error" in answer:
        raise ValueError(f"KataGo could not analyze the position: {answer['error']}")
    policy = answer.get("humanPolicy")
    if not policy or len(policy) != size * size + 1:
        raise ValueError("KataGo gave no human-like policy (is the human-like model set in KaTrain?)")
    return policy


def _move_at(index: int, size: int, color: str) -> Move:
    """Return the move of an index of KataGo's policy (the last index is the pass)."""
    if index == size * size:
        return Move(color, None)
    return Move.from_gtp(f"{GTP_COLUMNS[index % size]}{size - index // size}", color)
