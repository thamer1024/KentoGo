"""Tests for kentogo.seichi.seki."""

from kentogo.seichi.seki import neutral_points
from kentogo.seichi.territory import count_territory


def seki_board() -> dict:
    """A 9 x 9 board: on the left, a black and a white group in seki, each with one eye (A5 and E5),
    sharing the liberty C5; on the right, black territory (columns H and J)."""
    stones = {}
    for y in range(9):
        if y != 4:
            stones[(0, y)] = "B"  # Black's eye is A5.
            stones[(4, y)] = "W"  # White's eye is E5.
        stones[(1, y)] = "B"
        if y != 4:
            stones[(2, y)] = "B" if y < 4 else "W"  # C5 is the liberty they share.
        stones[(3, y)] = "W"
        stones[(5, y)] = "W"
        stones[(6, y)] = "B"
    return stones


def test_the_eyes_and_the_shared_liberty_of_a_seki_are_neutral():
    """The eyes of the groups in seki and their shared liberty are nobody's territory."""
    assert neutral_points(9, seki_board(), frozenset()) == {(0, 4), (2, 4), (4, 4)}


def test_no_territory_in_seki():
    """Counting only the surrounding color gives the eyes as territory; without the neutral points it does not."""
    stones = seki_board()
    assert (count_territory(9, stones).black, count_territory(9, stones).white) == (19, 1)
    neutral = neutral_points(9, stones, frozenset())
    assert (count_territory(9, stones, neutral=neutral).black, count_territory(9, stones, neutral=neutral).white) == (
        18,
        0,
    )


def test_a_group_marked_dead_is_not_seki():
    """When the white stones are marked dead, the black group lives with its territory: nothing is neutral."""
    stones = seki_board()
    white = frozenset(point for point, color in stones.items() if color == "W")
    assert neutral_points(9, stones, white) == frozenset()
