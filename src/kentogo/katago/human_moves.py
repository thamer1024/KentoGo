"""The move that a human of a rank would most likely play, from KataGo's human-like model.

KaTrain's human-like AI asks KataGo with the human-like model (KataGo started with -human-model) for
"humanPolicy" with a profile such as "rank_10k" (KaTrain 1.20.0, HumanStyleStrategy.generate_move,
which then chooses a move at random by these chances). Here the move with the biggest chance is taken,
so that the same position always gives the same move. The policy needs no search: one visit is read.
"""

from __future__ import annotations

import re

from kentogo.common.types import GTP_COLUMNS, Move, Position
from kentogo.katago.queries import position_query

HUMAN_VISITS = 1  # The human-like policy is that of the position itself.
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
    if "error" in answer:
        raise ValueError(f"KataGo could not analyze the position: {answer['error']}")
    policy = answer.get("humanPolicy")
    if not policy or len(policy) != size * size + 1:
        raise ValueError("KataGo gave no human-like policy (is the human-like model set in KaTrain?)")
    index = max(range(len(policy)), key=lambda point: policy[point])
    if index == size * size:
        return Move(color, None)
    return Move.from_gtp(f"{GTP_COLUMNS[index % size]}{size - index // size}", color)
