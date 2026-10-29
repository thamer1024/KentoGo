"""Tests for kentogo.mistakes.selection."""

from kentogo.mistakes.extract import ExtractSettings
from kentogo.mistakes.selection import MoveChoice, Selection, choose_moves


def test_is_decided():
    """A position is decided by a winrate of 99% or more of either side, or a lead of more than 40 points."""
    selection = Selection()
    assert selection.is_decided(0.99, None) and selection.is_decided(0.01, None)
    assert selection.is_decided(None, 40.5) and selection.is_decided(0.5, -41.0)
    assert not selection.is_decided(0.98, 40.0) and not selection.is_decided(None, None)
    assert Selection(decided_winrate=95.0, decided_lead=15.0).is_decided(0.96, None)


def test_open_positions_and_different_best_moves_first():
    """Decided positions and repeated best moves wait; the chosen moves are in the order played."""
    moves = [
        MoveChoice(10, 4.0, "D4"),
        MoveChoice(20, 9.0, "Q11", decided=True),
        MoveChoice(30, 8.0, "K10"),
        MoveChoice(40, 7.0, "K10"),  # The same best move as move 30, with a smaller loss.
        MoveChoice(50, 6.0, "C3"),
    ]
    assert choose_moves(moves, Selection(3)) == [10, 30, 50]


def test_the_others_fill_the_rest_by_loss():
    """When the first round has too few moves, the others come by their loss."""
    moves = [
        MoveChoice(20, 9.0, "Q11", decided=True),
        MoveChoice(21, 8.5, "Q11", decided=True),
        MoveChoice(30, 8.0, "K10"),
        MoveChoice(40, 7.0, "K10"),
    ]
    assert choose_moves(moves, Selection(3)) == [20, 21, 30]
    assert choose_moves(moves, Selection(10)) == [20, 21, 30, 40]
    assert choose_moves([], Selection(5)) == []


def test_unknown_best_moves_are_not_merged():
    """Moves without a known best move are never treated as the same."""
    assert choose_moves([MoveChoice(1, 5.0), MoveChoice(2, 4.0)], Selection(2)) == [1, 2]


def test_small_losses_wait():
    """Moves that lost less than the smallest loss of the quiz are chosen only when there is room."""
    moves = [MoveChoice(10, 9.0, "Q11", decided=True), MoveChoice(20, 1.5, "D4")]
    assert choose_moves(moves, Selection(1, 3.0)) == [10]
    assert choose_moves(moves, Selection(2, 3.0)) == [10, 20]
    quiz = ExtractSettings(problems_per_game=3, min_points_lost=4.0, decided_winrate=97.0, decided_lead=30.0)
    assert Selection.from_quiz(quiz) == Selection(3, 4.0, 97.0, 30.0)
