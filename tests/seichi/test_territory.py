"""Tests for kentogo.seichi.territory."""

from kentogo.common.types import Move
from kentogo.seichi.territory import TerritoryCount, count_territory, territory_owners


def stones(text: str) -> dict:
    """Make stones from text such as "B:C1 W:E1"."""
    moves = [Move.from_gtp(item[2:], item[0]) for item in text.split()]
    return {move.coord: move.color for move in moves}


def test_empty_board_has_no_territory():
    """An empty area with no stones around it belongs to no one."""
    assert count_territory(5, {}) == TerritoryCount(0, 0)


def test_wall_splits_the_board():
    """A black wall on column B and a white wall on column D: A is black's, E is white's, C is dame."""
    wall = " ".join(f"B:B{row} W:D{row}" for row in range(1, 6))
    assert count_territory(5, stones(wall)) == TerritoryCount(5, 5)


def test_stone_inside_territory_makes_it_no_ones():
    """A white stone inside black's area (a dead stone, not handled yet) makes that area count for no one."""
    wall = " ".join(f"B:B{row} W:D{row}" for row in range(1, 6))
    assert count_territory(5, stones(wall + " W:A3")) == TerritoryCount(0, 5)


def test_dame_mark_closes_an_open_boundary():
    """An open point in black's wall joins A to the dame column. Marked as dame, it closes the wall."""
    wall = " ".join(f"B:B{row}" for row in (1, 2, 4, 5)) + " " + " ".join(f"W:D{row}" for row in range(1, 6))
    assert count_territory(5, stones(wall)) == TerritoryCount(0, 5)
    dame = frozenset({Move.from_gtp("B3", "B").coord})
    assert count_territory(5, stones(wall), dame) == TerritoryCount(5, 5)
    assert Move.from_gtp("B3", "B").coord not in territory_owners(5, stones(wall), dame)


def test_majority_owners():
    """An area belongs to the color of most stones around it; a tie belongs to nobody."""
    from kentogo.seichi.territory import majority_owners

    stones = {(1, 0): "B", (1, 1): "B", (1, 2): "W"}  # Column B of a 3 x 3 board, mostly black.
    owners = majority_owners(3, stones)
    assert owners[(0, 0)] == "B" and owners[(2, 2)] == "B"
    assert majority_owners(3, {(1, 0): "B", (1, 2): "W"}) == {}  # One of each: nobody's.
