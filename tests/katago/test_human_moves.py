"""Tests for kentogo.katago.human_moves (the move a human of a rank would most likely play)."""

import pytest

from kentogo.common.types import Move, Position
from kentogo.katago.human_moves import HUMAN_VISITS, human_profile, human_query, most_likely_move


def test_human_profile():
    """A rank of KataGo's human-like model gives its profile; anything else gives none."""
    assert [human_profile(rank) for rank in ("10k", "20k", "1d", "9d")] == [
        "rank_10k",
        "rank_20k",
        "rank_1d",
        "rank_9d",
    ]
    assert [human_profile(rank) for rank in ("21k", "0k", "10d", "10級", "")] == ["", "", "", "", ""]


def test_human_query():
    """The query asks for the policy of the position after the moves, with the profile, as KaTrain's AI does."""
    position = Position(19, 6.5, "japanese", (), (Move.from_gtp("Q16", "B"),), "W")
    query = human_query(position, (Move.from_gtp("D4", "W"),), "rank_10k")
    assert query["includePolicy"] is True and query["maxVisits"] == HUMAN_VISITS
    assert query["overrideSettings"]["humanSLProfile"] == "rank_10k"
    assert query["moves"] == [["B", "Q16"], ["W", "D4"]]


def test_most_likely_move():
    """The policy goes row by row from the top row; its last value is the pass."""
    policy = [0.0] * 10
    policy[1] = 0.6  # The middle of the top row of a 3x3 board.
    assert most_likely_move({"humanPolicy": policy}, 3, "W") == Move.from_gtp("B3", "W")
    policy[9] = 0.9
    assert most_likely_move({"humanPolicy": policy}, 3, "W").is_pass
    policy = [0.0] * 10
    policy[6] = 0.5  # The left of the bottom row.
    assert most_likely_move({"humanPolicy": policy}, 3, "B") == Move.from_gtp("A1", "B")


@pytest.mark.parametrize("answer", [{"error": "no model"}, {"policy": [0.1] * 10}, {"humanPolicy": [0.1] * 5}])
def test_most_likely_move_without_a_human_like_policy(answer):
    """An error, or an answer without the human-like policy of the board, cannot give a move."""
    with pytest.raises(ValueError):
        most_likely_move(answer, 3, "B")
