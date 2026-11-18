"""Tests for kentogo.quiz.fight_stones (the chase of a group that is about to be captured)."""

from kentogo.common.types import Move, Position
from kentogo.quiz.fight_stones import CHASE_BROKEN, CHASE_CAPTURED, CHASE_GOING, ChaseTracker, board_after

# White's stones at A1 (setup) and E5 (a move); black to play.
POSITION = Position(9, 6.5, "japanese", (Move("W", (0, 0)),), (Move("W", (4, 4)),), "B")
B1 = Move("B", (1, 0))
E6 = Move("W", (4, 5))
A2 = Move("B", (0, 1))
BLACKS_A1 = {(0, 0): 0.9}


def chasing() -> ChaseTracker:
    """A tracker that chases A1 after black's B1."""
    tracker = ChaseTracker(POSITION)
    tracker.update((B1,), BLACKS_A1)
    return tracker


def test_the_board_after_the_moves_skips_a_pass_and_a_move_that_is_not_allowed():
    board = board_after(POSITION, (B1, Move("B", None), Move("B", (0, 0))))  # A pass; a stone on a stone.
    assert board.stone_at((1, 0)) == "B" and board.stone_at((0, 0)) == "W"


def test_a_chase_starts_next_to_the_last_move():
    tracker = chasing()
    assert tracker.active and tracker.result == CHASE_GOING
    assert tracker.local_moves((B1,), "W") == ["A2", "A3", "B2"]  # The liberty A2, and the empty points next to it.


def test_no_chase_without_the_areas_or_with_room():
    tracker = ChaseTracker(POSITION)
    tracker.update((B1,), {(0, 0): 0.4})  # Not given to black firmly enough.
    assert not tracker.active and tracker.result is None
    tracker.update((Move("B", (4, 3)),), {(4, 4): 0.9})  # E5 keeps three liberties.
    assert not tracker.active and tracker.local_moves((B1,), "W") == []


def test_a_chase_goes_on_with_many_liberties_until_the_group_is_captured():
    tracker = chasing()
    moves = (B1, E6)
    tracker.update(moves, BLACKS_A1)
    assert tracker.active
    moves = (*moves, A2)
    tracker.update(moves, BLACKS_A1)
    assert not tracker.active and tracker.result == CHASE_CAPTURED
    assert tracker.local_moves(moves, "W") == []


def test_a_chase_is_broken_when_the_group_is_no_longer_given_to_the_chaser():
    tracker = chasing()
    tracker.update((B1,), {(0, 0): 0.2})
    assert not tracker.active and tracker.result == CHASE_BROKEN
    tracker.update((B1,), BLACKS_A1)  # Not started again after the same moves.
    assert not tracker.active
    tracker.update((B1, E6), BLACKS_A1)  # After one more move it can start again: B1, the move before, is next to A1.
    assert tracker.active


def test_a_chase_starts_with_half_of_the_group_and_survives_a_dip():
    tracker = ChaseTracker(POSITION)
    tracker.update((B1,), {(0, 0): 0.5})
    assert tracker.active and tracker.share == 0.5
    tracker.update((B1, E6), {(0, 0): 0.3})
    assert tracker.active and tracker.share == 0.3
