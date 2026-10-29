"""Tests for kentogo.seichi.stray_stones."""

from kentogo.common.types import Move, Position
from kentogo.seichi import arrangement as arrangement_module
from kentogo.seichi.arrangement import Arrangement
from kentogo.seichi.stray_stones import stray_stones


def test_a_stone_in_the_other_players_territory_is_found():
    """A white stone whose empty neighbors are all black territory is stray; the walls are not."""
    stones = {(1, 0): "B", (1, 1): "B", (1, 2): "B", (2, 0): "W", (2, 1): "W", (2, 2): "W", (0, 1): "W"}
    owners = {(0, 0): "B", (0, 2): "B"}
    assert stray_stones(3, stones, owners) == {(0, 1)}


def test_a_stone_next_to_its_own_territory_or_nobodys_point_is_not_stray():
    """A stone with an empty neighbor of its own color, or of nobody, stays where it is."""
    stones = {(1, 1): "W"}
    assert stray_stones(3, stones, {(0, 1): "B", (1, 0): "B", (2, 1): "B", (1, 2): "W"}) == set()
    assert stray_stones(3, stones, {(0, 1): "B", (1, 0): "B", (2, 1): "B"}) == set()  # (1, 2) is nobody's.


def test_the_computer_leaves_out_the_last_parts_when_they_leave_a_stray_stone(monkeypatch):
    """When the full seichi leaves a stone in the other territory, it is made again with fewer parts."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement.toggle_dead(Move.from_gtp("A2", "B").coord)
    arrangement.remove_dead()
    calls = []

    def stray_first_time(size, stones, owners):
        calls.append(dict(stones))
        return {(0, 0)} if len(calls) == 1 else set()

    monkeypatch.setattr(arrangement_module, "stray_stones", stray_first_time)
    plan = arrangement.plan_auto()
    assert len(calls) == 2
    assert not any(step.kind == "swap" for step in plan.result.steps)  # Made without the clear boundary.
