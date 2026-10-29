"""Tests for kentogo.seichi.final_position."""

import pytest

from kentogo.common.types import Move
from kentogo.seichi.final_position import ended_by_counting, read_finished_game

PASSES = (Move("B", None), Move("W", None))


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("B+3.5", True),
        ("W+12", True),
        ("w+0.5", True),
        ("0", True),
        ("Draw", True),
        ("B+R", False),
        ("W+Resign", False),
        ("B+T", False),
        ("W+F", False),
        ("Void", False),
        ("?", False),
    ],
)
def test_result_decides(result, expected):
    """A score or a draw is counted. A resignation, time, forfeit or unknown result is not."""
    assert ended_by_counting(result, ()) is expected


def test_without_result_two_passes_decide():
    """Without a result, the game must end with two passes."""
    move = Move("B", (3, 3))
    assert ended_by_counting("", (move, *PASSES))
    assert not ended_by_counting("", (move, Move("W", None)))
    assert not ended_by_counting("", ())


def test_read_finished_game(tmp_path):
    """A game that ended by counting is read with its final position; a resigned game is not used."""
    (tmp_path / "a.sgf").write_text("(;SZ[9]RE[B+R];B[ee];W[cc])", encoding="utf-8")
    (tmp_path / "c.sgf").write_text("(;SZ[9]KM[7]RE[W+2.5];B[ee];W[cc];B[];W[])", encoding="utf-8")
    assert read_finished_game(tmp_path / "a.sgf") is None
    game = read_finished_game(tmp_path / "c.sgf")
    assert game.result == "W+2.5" and game.position.size == 9 and game.position.komi == 7
    assert [move.gtp() for move in game.position.moves[:2]] == ["E5", "C7"]
    assert game.position.next_color == "B"


def test_no_finished_game(tmp_path):
    """Without a game that ended by counting, there is none."""
    (tmp_path / "a.sgf").write_text("(;SZ[9]RE[W+R];B[ee])", encoding="utf-8")
    assert read_finished_game(tmp_path / "a.sgf") is None
