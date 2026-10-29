"""Tests for kentogo.katago.queries."""

import pytest

from kentogo.common.types import Move, Position
from kentogo.katago.queries import best_sequence, points_lost, position_query, root_score

HANDICAP = (Move.from_gtp("D4", "B"), Move.from_gtp("Q16", "B"))


def test_query_of_a_position():
    """The query has the board, the rules, the stones and the moves, and analyzes the last turn."""
    position = Position(19, 6.5, "cn", (), (Move.from_gtp("Q16", "B"), Move.from_gtp("D4", "W")), "B")
    query = position_query(position, (Move.from_gtp("Q4", "B"),), max_visits=300)
    assert query == {
        "rules": "chinese",
        "komi": 6.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "initialStones": [],
        "initialPlayer": "B",
        "moves": [["B", "Q16"], ["W", "D4"], ["B", "Q4"]],
        "analyzeTurns": [3],
        "maxVisits": 300,
        "overrideSettings": {"reportAnalysisWinratesAs": "BLACK"},
    }


def test_query_with_handicap_and_no_moves():
    """With handicap stones and no moves, the first player is the player to move (white)."""
    position = Position(19, 0.5, "japanese", HANDICAP, (), "W")
    query = position_query(position)
    assert query["initialStones"] == [["B", "D4"], ["B", "Q16"]]
    assert (query["initialPlayer"], query["moves"], query["analyzeTurns"]) == ("W", [], [0])


def test_query_with_json_rules():
    """KataGo's rule settings written as JSON are passed as a dict."""
    position = Position(19, 7.0, '{"ko": "POSITIONAL", "suicide": true}', (), (), "B")
    assert position_query(position)["rules"] == {"ko": "POSITIONAL", "suicide": True}


def test_query_with_wide_root_noise():
    """KaTrain's wide_root_noise setting is passed to KataGo when it is given."""
    position = Position(19, 6.5, "japanese", (), (), "B")
    assert position_query(position, wide_root_noise=0.04)["overrideSettings"] == {
        "reportAnalysisWinratesAs": "BLACK",
        "wideRootNoise": 0.04,
    }


def test_root_score():
    """The score lead is read from the root of the answer."""
    assert root_score({"id": "1", "rootInfo": {"scoreLead": -2.5, "winrate": 0.4}}) == -2.5


@pytest.mark.parametrize("answer", [{"id": "1", "error": "bad query"}, {"id": "1", "moveInfos": []}])
def test_root_score_of_a_bad_answer(answer):
    """An error answer, or an answer without a score, is an error."""
    with pytest.raises(ValueError):
        root_score(answer)


def test_best_sequence():
    """The sequence of the move ranked first is returned, whatever the order of the list."""
    answer = {
        "moveInfos": [
            {"move": "C3", "order": 1, "pv": ["C3", "D4"]},
            {"move": "Q4", "order": 0, "pv": ["Q4", "D16", "C17"]},
        ]
    }
    assert best_sequence(answer) == ("Q4", "D16", "C17")
    assert best_sequence({"moveInfos": []}) == ()


def test_points_lost_for_black_and_white():
    """The loss is seen from the player of the move, as in KaTrain."""
    assert points_lost("B", 3.0, -5.0) == 8.0  # Black was 3 ahead, and is 5 behind after the move.
    assert points_lost("W", 3.0, 10.0) == 7.0  # Black led by 3, and leads by 10 after white's move.
    assert points_lost("B", 3.0, 3.2) == pytest.approx(-0.2)  # A tiny negative loss can happen.
