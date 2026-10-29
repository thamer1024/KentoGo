"""Tests for kentogo.gui.step_motion."""

import pytest

from kentogo.gui.step_motion import StoneMotion, between, eased, step_motions, without_moving
from kentogo.seichi.arrangement import FillStep

NO_PRISONERS = {"B": 0, "W": 0}


def step(kind: str, color: str, points: tuple, stones: dict | None = None) -> FillStep:
    """Make a step of the computer's seichi."""
    return FillStep(kind, color, points, stones or {}, NO_PRISONERS)


def test_moving_stones_of_each_kind_of_step():
    """Moved stones slide from their point, prisoners from their tray; a swap moves two stones."""
    assert step_motions(step("move", "B", ((0, 0), (2, 3)))) == (StoneMotion("B", (0, 0), (2, 3)),)
    assert step_motions(step("place", "W", ((4, 4),))) == (StoneMotion("W", None, (4, 4)),)
    assert step_motions(step("exchange", "B", ((1, 1), (5, 5)))) == (StoneMotion("B", (1, 1), (5, 5)),)
    swap = step("swap", "B", ((1, 1), (5, 5)), {(1, 1): "W", (5, 5): "B"})
    assert step_motions(swap) == (StoneMotion("B", (1, 1), (5, 5)), StoneMotion("W", (5, 5), (1, 1)))


def test_steps_without_moving_stones():
    """Stones taken off, and a stone only changed to the other color, do not move."""
    assert step_motions(step("capture", "W", ((0, 0), (0, 1)))) == ()
    assert step_motions(step("exchange", "B", ((3, 3),))) == ()


def test_moving_stones_are_not_on_the_board_yet():
    """While they move, the stones of the step are not drawn on their points."""
    stones = {(0, 0): "B", (2, 3): "B", (5, 5): "W"}
    assert without_moving(stones, (StoneMotion("B", (1, 1), (2, 3)),)) == {(0, 0): "B", (5, 5): "W"}


@pytest.mark.parametrize("fraction, expected", [(-1, 0.0), (0, 0.0), (0.5, 0.5), (1, 1.0), (2, 1.0)])
def test_eased(fraction, expected):
    """The move starts and ends where it should, and is half way at half of the time."""
    assert eased(fraction) == expected


def test_between():
    """The stone goes in a straight line, slowly at the start."""
    assert between((0, 0), (10, 20), 0.5) == (5, 10)
    assert between((0, 0), (10, 20), 1) == (10, 20)
    assert 0 < between((0, 0), (10, 0), 0.1)[0] < 1
