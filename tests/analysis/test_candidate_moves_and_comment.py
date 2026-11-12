"""Tests for kentogo.analysis.candidate_moves and analysis.kentogo_comment (KentoGo's comment on a move)."""

from kentogo.analysis.candidate_moves import policy_ranking, top_candidate
from kentogo.analysis.kentogo_comment import ENGLISH, JAPANESE, CommentedMove, kentogo_move_comment
from kentogo.common.types import Move

SIZE = (5, 5)


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
    commented = CommentedMove(5, Move.from_gtp("A1", "B"), 4.2)
    assert kentogo_move_comment(commented, BEFORE, AFTER_A1, SIZE, ENGLISH).splitlines() == [
        "Move 5: B A1",
        "Points lost: 4.2",
        "Best move: C3 (B+1.2, win rate B 56.0%)",
        "Predicted sequence: BC3 B2",
        "After the move: W+3.0, win rate W 70.0%",
        "Policy rank: 2 (2.0%)",
        "Policy's first move: C3 (50.0%)",
    ]


def test_comment_on_the_best_move_in_japanese():
    commented = CommentedMove(5, Move.from_gtp("C3", "B"), 0.0)
    lines = kentogo_move_comment(commented, BEFORE, AFTER_C3, SIZE, JAPANESE).splitlines()
    assert lines[:2] == ["第5手 黒 C3", "最善手でした"]
    assert "第一感: 1位（50.0%）" in lines and not any(line.startswith("第一感の1位") for line in lines)


def test_a_small_loss_is_not_written_and_a_move_taken_back_is():
    commented = CommentedMove(5, Move.from_gtp("A1", "B"), 0.4, taken_back=True)
    lines = kentogo_move_comment(commented, BEFORE, AFTER_A1, SIZE, JAPANESE).splitlines()
    assert not any(line.startswith("損失") for line in lines)
    assert lines[-1] == "KaTrainの待ったで戻した手です"


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
