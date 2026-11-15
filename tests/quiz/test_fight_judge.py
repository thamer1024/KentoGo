"""Tests for kentogo.quiz.fight_judge (the rules of the local fight problems)."""

from kentogo.common.types import Move, Position
from kentogo.mistakes.local_fight import KIND_BOUNDARY, KIND_LIFE_DEATH, LocalFight
from kentogo.quiz.fight_judge import (
    OUTCOME_LOST,
    OUTCOME_SCORE,
    OUTCOME_WON,
    ended_outcome,
    fight_places,
    fight_won,
    is_near,
    is_settled,
    judged_points,
    most_moves,
    score_loss,
)

POSITION = Position(9, 6.5, "japanese", (), (Move("W", (4, 4)),), "B")


def fight(kind: str = KIND_LIFE_DEATH, moves: int = 2) -> LocalFight:
    """Black's stones A1, B1 and C1 died in the game; the empty points A2 and B2 were black's."""
    line = (Move("B", (0, 2)), Move("W", (1, 2)), Move("B", (8, 8)))
    return LocalFight("id", "a.sgf", 2, POSITION, kind, ("A1", "B1", "C1"), (), ("A2", "B2"), moves, 0.5, line)


def test_judged_points():
    assert judged_points(fight()) == [(0, 0), (1, 0), (2, 0)]  # The stones.
    assert judged_points(fight(KIND_BOUNDARY)) == [(0, 1), (1, 1)]  # The empty points.


def test_settled_and_won():
    points = [(0, 0), (1, 0), (2, 0)]
    alive = {point: 0.9 for point in points}
    assert is_settled(alive, points) and fight_won(alive, points, "B") and not fight_won(alive, points, "W")
    assert not is_settled(alive | {(2, 0): 0.6}, points)
    assert fight_won(alive | {(2, 0): -0.9}, points * 2 + [(2, 0)], "B") is False  # 6 of 7 is less than 80%.
    assert fight_won({}, [], "B") is False


def test_moves_near_the_fight():
    places = fight_places(fight(), ())
    assert (0, 2) in places and (8, 8) not in places  # Only the fight's moves of the game (2 moves) count.
    assert is_near(Move("B", (3, 3)), places) and not is_near(Move("B", (6, 6)), places)
    assert not is_near(Move("B", None), places)  # A pass leaves the fight.
    assert most_moves(fight()) == 1 + 4 and most_moves(fight(moves=3)) == 2 + 4
    played = (Move("B", (8, 8)), Move("W", (7, 8)), Move("B", (1, 3)))  # J9 and H9 are away; B4 is near.
    assert fight_places(fight(), played) == places + [(1, 3)]


def test_ended_outcome():
    alive = {(0, 0): 0.9, (1, 0): 0.9, (2, 0): 0.9}
    assert ended_outcome(alive, fight(), 1.0, 3.0).kind == OUTCOME_WON
    assert ended_outcome(alive, fight(), 4.0, 3.0).kind == OUTCOME_SCORE  # Alive, but too much was lost.
    assert ended_outcome(alive, fight(), None, 3.0).correct
    assert ended_outcome({}, fight(), 0.0, 3.0).kind == OUTCOME_LOST
    assert score_loss(2.0, -1.0, "B") == 3.0 and score_loss(2.0, -1.0, "W") == -3.0
