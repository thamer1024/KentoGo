"""Tests for kentogo.katago.human_moves (the move a human of a rank would most likely play)."""

import pytest

from kentogo.common.types import Move, Position
from kentogo.katago.human_moves import (
    HUMAN_VISITS,
    MAX_CANDIDATES,
    Candidate,
    candidate_moves,
    choose_natural,
    human_profile,
    human_query,
    losses_of,
    most_likely_move,
    move_scores,
    restricted_query,
)


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
    with pytest.raises(ValueError):
        candidate_moves(answer, 3, "B")


def test_candidate_moves_are_the_moves_that_are_not_much_less_likely_than_the_likeliest():
    """Moves with at least NATURAL_RATIO of the likeliest one's chance, from the likeliest; a pass is not one."""
    policy = [0.0] * 10
    policy[1], policy[4], policy[6], policy[9] = 0.5, 0.3, 0.03, 0.04  # B3, B2, A1 (0.03 > 0.025), and the pass.
    policy[0] = 0.02  # Below 0.05 of 0.5: not a candidate.
    candidates = candidate_moves({"humanPolicy": policy}, 3, "B")
    assert [c.move.gtp() for c in candidates] == ["B3", "B2", "A1"]
    assert [c.chance for c in candidates] == [0.5, 0.3, 0.03]
    single = candidate_moves({"humanPolicy": [0.0, 1.0] + [0.0] * 8}, 3, "B")
    assert single == (Candidate(Move.from_gtp("B3", "B"), 1.0),)


def test_candidate_moves_have_a_limit_and_a_pass_alone_when_it_is_the_most_likely():
    """At most MAX_CANDIDATES moves; if the pass is the most likely move, it is the only candidate."""
    flat = [0.01] * 82  # Every move is natural: the limit stops it (a 9 x 9 board).
    assert len(candidate_moves({"humanPolicy": flat}, 9, "B")) == MAX_CANDIDATES
    policy = [0.0] * 10
    policy[9], policy[1] = 0.6, 0.4
    [only] = candidate_moves({"humanPolicy": policy}, 3, "W")
    assert only.move.is_pass


def test_restricted_query_allows_only_the_candidates():
    """The query is KataGo's own search that may play only the candidates, for the player of the candidates."""
    position = Position(19, 6.5, "japanese", (), (Move.from_gtp("Q16", "B"),), "W")
    candidates = (Move.from_gtp("D4", "W"), Move.from_gtp("C16", "W"))
    query = restricted_query(position, (), candidates, 100)
    assert query["allowMoves"] == [{"player": "W", "moves": ["D4", "C16"], "untilDepth": 1}]
    assert query["maxVisits"] == 100 and "humanSLProfile" not in query["overrideSettings"]
    assert "wideRootNoise" not in query["overrideSettings"]


CANDIDATES = tuple(
    Candidate(Move.from_gtp(point, "B"), chance) for point, chance in (("D4", 0.5), ("C16", 0.3), ("Q4", 0.2))
)


def test_choose_natural_takes_the_least_loss_and_among_equals_the_most_likely():
    """The least loss wins; moves within LOSS_TOLERANCE of it are equal, and the most likely of them is played."""
    assert choose_natural(CANDIDATES, {"D4": 1.0, "C16": 0.0, "Q4": 0.5}) == CANDIDATES[1]
    assert choose_natural(CANDIDATES, {"D4": 0.25, "C16": 0.0, "Q4": 0.0}) == CANDIDATES[0]  # Within 0.3: equal.
    assert choose_natural(CANDIDATES, {"D4": 0.31, "C16": 0.0, "Q4": 0.0}) == CANDIDATES[1]
    assert choose_natural(CANDIDATES, {"Q4": 0.4, "C16": 2.0}) == CANDIDATES[2]  # D4 is not known.
    assert choose_natural(CANDIDATES, {}) is None


def test_the_losses_are_against_the_best_move_for_the_player():
    """The scores are from black's side: black's best is the highest, white's the lowest."""
    answer = {"moveInfos": [{"move": "D4", "scoreLead": 3.0}, {"move": "C16", "scoreLead": 1.5}, {"move": "Q4"}]}
    scores = move_scores(answer)
    assert scores == {"D4": 3.0, "C16": 1.5}  # A move without a score is left out.
    assert losses_of(scores, "B") == {"D4": 0.0, "C16": 1.5}
    assert losses_of(scores, "W") == {"D4": 1.5, "C16": 0.0}
    assert move_scores({"moveInfos": []}) == {} and losses_of({}, "B") == {}
    with pytest.raises(ValueError):
        move_scores({"error": "stopped"})
