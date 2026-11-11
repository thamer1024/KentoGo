"""The values of a position in a game with handicap stones, counted from the start of the game.

With handicap stones (setup stones), black leads by many points and has a high winrate from the
start: with 6 stones, KataGo gives black a lead of about 18 points and a winrate of about 90% before
the first move. So whether a game is already decided (see mistakes.selection.Selection.is_decided)
is told there by the lead gained since the start (the lead minus the lead before the first move),
and not by the winrate.
"""

from __future__ import annotations


def from_start(winrate: float | None, lead: float | None, start_lead: float | None) -> tuple[None, float | None]:
    """Return the values of a position of a handicap game for telling whether it is decided.

    Args:
        winrate: Black's winrate of the position (not used).
        lead: Black's score lead of the position, or None if not known.
        start_lead: Black's score lead before the first move, or None if not known.

    Returns:
        (None, the lead gained since the start), or (None, None) when either lead is not known.
    """
    del winrate  # The winrate is high from the start: it does not tell that the game is decided.
    if lead is None or start_lead is None:
        return None, None
    return None, lead - start_lead
