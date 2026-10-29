"""How many losses of each size a player of each rank should allow in one game (from the user's script).

The numbers were found by the user from games on Fox Weiqi (4_blunder_stats.py). For each
rank, there is a pair (goal, limit) for each size of loss in material.LOSS_SIZES
(20, 12, 10, 8, 6 and 3 points or more):

- goal: the number to aim at (the median of players one rank higher).
- limit: the number not to go over (75% of the players of this rank stay within it).

Where a higher rank had a larger number, it was set to the number of the rank below.
"""

from __future__ import annotations

import re

from kentogo.commentary.material import LOSS_SIZES

_TABLE = {
    "20k": ((0, 1), (1, 3), (1, 5), (2, 7), (5, 11), (11, 23)),
    "19k": ((0, 1), (1, 3), (1, 5), (2, 7), (5, 11), (11, 23)),
    "18k": ((0, 1), (1, 3), (1, 5), (2, 7), (5, 11), (11, 23)),
    "17k": ((0, 1), (0, 2), (1, 3), (2, 5), (4, 9), (10, 22)),
    "16k": ((0, 1), (0, 2), (0, 3), (1, 4), (3, 7), (9, 17)),
    "15k": ((0, 0), (0, 1), (0, 2), (1, 4), (3, 7), (9, 17)),
    "14k": ((0, 0), (0, 1), (0, 2), (1, 4), (3, 7), (9, 17)),
    "13k": ((0, 0), (0, 1), (0, 2), (1, 4), (3, 7), (9, 17)),
    "12k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 6), (9, 16)),
    "11k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 6), (8, 16)),
    "10k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "9k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "8k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "7k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "6k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "5k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "4k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "3k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 14)),
    "2k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (8, 12)),
    "1k": ((0, 0), (0, 1), (0, 2), (1, 3), (2, 5), (7, 12)),
    "1d": ((0, 0), (0, 1), (0, 2), (1, 3), (1, 5), (6, 11)),
    "2d": ((0, 0), (0, 1), (0, 1), (0, 2), (1, 4), (5, 11)),
    "3d": ((0, 0), (0, 1), (0, 1), (0, 2), (1, 3), (5, 8)),
    "4d": ((0, 0), (0, 1), (0, 1), (0, 2), (1, 3), (4, 8)),
    "5d": ((0, 0), (0, 1), (0, 1), (0, 1), (0, 3), (2, 7)),
    "6d": ((0, 0), (0, 1), (0, 1), (0, 1), (0, 2), (2, 7)),
    "7d": ((0, 0), (0, 1), (0, 1), (0, 1), (0, 2), (2, 6)),
    "8d": ((0, 0), (0, 0), (0, 0), (0, 1), (0, 1), (1, 4)),
    "9d": ((0, 0), (0, 0), (0, 0), (0, 0), (0, 1), (1, 2)),
}

# The ranks, from the weakest: "20k" ... "1k", "1d" ... "9d".
RANKS = tuple(_TABLE)


def normalize_rank(text: str) -> str:
    """Turn a rank such as "18k", "18K", "18級", "18级" (Fox Weiqi), "1d" or "1段" into the form of RANKS.

    Returns:
        The rank, or "" if the text is not a rank in RANKS.
    """
    match = re.fullmatch(r"\s*(\d{1,2})\s*([kKdD級级段])\s*", text)
    if not match:
        return ""
    rank = f"{int(match[1])}{'k' if match[2] in 'kK級级' else 'd'}"
    return rank if rank in _TABLE else ""


def rank_label(rank: str) -> str:
    """Return a rank in Japanese, such as "18級" or "1段" ("" if it is not a rank)."""
    rank = normalize_rank(rank)
    return f"{rank[:-1]}{'級' if rank.endswith('k') else '段'}" if rank else ""


def targets_for(rank: str) -> dict[int, tuple[int, int]] | None:
    """Return the (goal, limit) for each size of loss for a rank, or None if the rank is not in the table."""
    pairs = _TABLE.get(normalize_rank(rank))
    return dict(zip(LOSS_SIZES, pairs, strict=True)) if pairs else None
