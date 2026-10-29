"""Tests for kentogo.common.types."""

import pytest

from kentogo.common.types import Move, Position, moves_from_gtp, opponent


def test_opponent():
    """The other color is returned."""
    assert opponent("B") == "W"
    assert opponent("W") == "B"


def test_moves_from_gtp():
    """A sequence of points becomes moves with the colors taking turns."""
    assert moves_from_gtp(["D16", "Q4", "pass"], "W") == (
        Move.from_gtp("D16", "W"),
        Move.from_gtp("Q4", "B"),
        Move("W", None),
    )
    assert moves_from_gtp([], "B") == ()


def test_gtp_coordinates():
    """GTP coordinates count from the lower left, and the column "I" is skipped."""
    assert Move.from_gtp("A1", "B").coord == (0, 0)
    assert Move.from_gtp("J10", "W").coord == (8, 9)
    assert Move.from_gtp("t19", "B").coord == (18, 18)
    assert Move("B", (15, 15)).gtp() == "Q16"


def test_gtp_pass():
    """A pass has no point."""
    move = Move.from_gtp("pass", "W")
    assert move.is_pass
    assert move.gtp() == "pass"


def test_gtp_large_board():
    """Large boards use two letters for a column."""
    move = Move.from_gtp("AA30", "B")
    assert move.coord == (25, 29)
    assert move.gtp() == "AA30"


def test_gtp_wrong_text():
    """A text that is not a GTP point is an error."""
    with pytest.raises(ValueError):
        Move.from_gtp("I5", "B")
    with pytest.raises(ValueError):
        Move.from_gtp("Q", "B")


def test_sgf_coordinates():
    """SGF coordinates count rows from the top."""
    assert Move.from_sgf("pd", "B", 19) == Move.from_gtp("Q16", "B")
    assert Move.from_sgf("aa", "W", 19).coord == (0, 18)
    assert Move.from_sgf("aa", "W", 9).coord == (0, 8)
    assert Move("B", (15, 15)).sgf(19) == "pd"


def test_sgf_pass():
    """An empty text is a pass, and "tt" is also a pass on boards up to 19x19."""
    assert Move.from_sgf("", "B", 19).is_pass
    assert Move.from_sgf("tt", "B", 19).is_pass
    assert not Move.from_sgf("tt", "B", 21).is_pass
    assert Move("B", None).sgf(19) == ""


def test_sgf_wrong_text():
    """A text that is not an SGF point is an error."""
    with pytest.raises(ValueError):
        Move.from_sgf("p", "B", 19)


def test_data_cannot_be_changed():
    """Moves and positions are immutable, so they can be shared safely."""
    move = Move("B", (3, 3))
    position = Position(19, 6.5, "japanese", (), (move,), "W")
    with pytest.raises(AttributeError):
        move.color = "W"
    with pytest.raises(AttributeError):
        position.next_color = "B"
