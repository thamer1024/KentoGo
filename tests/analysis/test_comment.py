"""Tests for kentogo.analysis.comment (KaTrain's comment on an analyzed move)."""

from kentogo.analysis.comment import (
    CommentedMove,
    format_score,
    move_comment,
    policy_ranking,
    top_candidate,
)
from kentogo.common.types import Move
from kentogo.record.katrain_texts import KATRAIN_TEXTS

SIZE = (5, 5)
EN = KATRAIN_TEXTS["en"]


def policy(values: dict[int, float]) -> list[float]:
    """A policy of the 5x5 board (rows from the top, then the pass), 0.01 except the given indexes."""
    numbers = [0.01] * 26
    for index, value in values.items():
        numbers[index] = value
    return numbers


# C3 is index 12 (third row from the top, third column); A1 is index 20 (bottom row, first column).
BEFORE = {
    "root": {"scoreLead": 1.0, "winrate": 0.55},
    "moves": {
        "A1": {"move": "A1", "order": 999, "scoreLead": -3.0, "winrate": 0.3},
        "C3": {"move": "C3", "order": 0, "scoreLead": 1.2, "winrate": 0.56, "pv": ["C3", "B2"]},
    },
    "policy": policy({12: 0.5, 20: 0.02, 25: 0.0}),
}
AFTER_A1 = {
    "root": {"scoreLead": -3.0, "winrate": 0.3},
    "moves": {"B2": {"order": 0, "scoreLead": -3.1, "winrate": 0.3, "pv": ["B2"]}},
}
AFTER_C3 = {"root": {"scoreLead": 1.2, "winrate": 0.56}, "moves": {}}


def test_comment_on_a_mistake():
    commented = CommentedMove(3, Move.from_gtp("A1", "B"))
    assert move_comment(commented, BEFORE, AFTER_A1, SIZE, "en") == (
        "Move 3: B A1\n"
        "Score: W+3.0\n"
        "Win rate: W 70.0%\n"
        "Estimated point loss: 4.0\n"
        "Predicted top move was C3 (B+1.2).\n"
        "PV: BC3 B2\n"
        "Move was #2 according to policy  (2.00%).\n"
        "Top policy move was C3 (50.0%).\n"
    )


def test_comment_on_the_best_move_in_japanese():
    commented = CommentedMove(3, Move.from_gtp("C3", "B"))
    assert move_comment(commented, BEFORE, AFTER_C3, SIZE, "jp") == (
        "手数3: B C3\n目差：黒+1.2\n勝率：黒 56.0%\n最善手\n予想手順：BC3 B2\n第一感では1位  (50.00%)\n"
    )


def test_small_loss_and_unknown_language():
    """A loss of 0.5 points or less is not written; a language without texts uses English."""
    after = {"root": {"scoreLead": 0.6, "winrate": 0.5}}
    text = move_comment(CommentedMove(3, Move.from_gtp("A1", "B")), BEFORE, after, SIZE, "xx")
    assert "point loss" not in text and text.startswith("Move 3: B A1\nScore: B+0.6\nWin rate: W 50.0%\n")


def test_teaching_undo_lines():
    """A move taken back gets KaTrain's two lines; the sequence is the opponent's, from the position after it."""
    commented = CommentedMove(3, Move.from_gtp("A1", "B"), auto_undo=True)
    text = move_comment(commented, BEFORE, AFTER_A1, SIZE, "en")
    assert text.endswith("Move was automatically undone in teaching mode.\nPredicted follow-up: WB2\n")


def test_top_candidate_by_order_then_loss_and_by_policy_without_moves():
    assert top_candidate(BEFORE, "B", SIZE)["move"] == "C3"
    moves = {"A": {"order": 0, "scoreLead": -1.0, "winrate": 0.4}, "B": {"order": 0, "scoreLead": 2.0, "winrate": 0.6}}
    tied = {"root": {"scoreLead": 0.0, "winrate": 0.5}, "moves": moves}
    assert top_candidate(tied, "B", SIZE)["scoreLead"] == 2.0  # The smaller loss first for black.
    no_moves = {"root": {"scoreLead": 1.0}, "moves": {}, "policy": BEFORE["policy"]}
    assert top_candidate(no_moves, "B", SIZE) == {
        "scoreLead": 1.0,
        "pointsLost": 0,
        "winrateLost": 0,
        "order": 0,
        "move": "C3",
        "pv": ["C3"],
    }
    assert top_candidate({"root": {}, "moves": {}}, "W", SIZE)["move"] == "pass"


def test_policy_ranking_keeps_katrains_order_for_equal_values():
    """Equal values stay column by column from the left, each from the bottom, with the pass last."""
    ranking = policy_ranking(BEFORE, "B", SIZE)
    assert [move.gtp() for _, move in ranking[:4]] == ["C3", "A1", "A2", "A3"]
    assert ranking[-1] == (0.0, Move("B", None))
    assert policy_ranking({"policy": None}, "B", SIZE) == []


def test_format_score_keeps_zero():
    """A score of 0 is written as 0 (KaTrain writes the node's own score instead)."""
    assert format_score(0.0, -2.0, EN) == "B+0.0"
    assert format_score(None, -2.0, EN) == "W+2.0"
    assert format_score(None, None, EN) is None
    assert format_score(-0.04, None, EN) == "W+0.0"
