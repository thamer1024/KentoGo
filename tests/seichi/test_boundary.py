"""Tests for kentogo.seichi.boundary."""

from kentogo.seichi.boundary import clear_boundary

SIZE = 5


def two_walls(swapped: bool) -> tuple[dict, dict]:
    """A 5 x 5 board: black territory on column A, a black wall on B, a white wall on C, white territory on D-E.

    With swapped, the stones on B3 and C3 have each other's color.
    """
    stones = {(1, y): "B" for y in range(SIZE)} | {(2, y): "W" for y in range(SIZE)}
    if swapped:
        stones[(1, 2)], stones[(2, 2)] = "W", "B"
    owners = {(0, y): "B" for y in range(SIZE)} | {(x, y): "W" for x in (3, 4) for y in range(SIZE)}
    return stones, owners


def test_mixed_stones_are_swapped_back():
    """A white stone in the black wall and a black stone in the white wall are swapped."""
    stones, owners = two_walls(swapped=True)
    assert clear_boundary(SIZE, stones, owners) == [((2, 2), (1, 2))]


def test_a_clear_boundary_needs_nothing():
    """Straight walls of each color: no swap."""
    stones, owners = two_walls(swapped=False)
    assert clear_boundary(SIZE, stones, owners) == []
