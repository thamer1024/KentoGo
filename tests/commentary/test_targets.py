"""Tests for kentogo.commentary.targets."""

from kentogo.commentary.targets import RANKS, normalize_rank, rank_label, targets_for


def test_normalize_rank():
    """Ranks written in several ways are understood, and other texts are not."""
    assert [normalize_rank(text) for text in ("18k", "18K", " 18級 ", "1d", "1段", "09k", "5级")] == [
        "18k",
        "18k",
        "18k",
        "1d",
        "1d",
        "9k",
        "5k",
    ]
    assert [normalize_rank(text) for text in ("", "25k", "10d", "18", "abc")] == ["", "", "", "", ""]
    assert (RANKS[0], RANKS[-1], len(RANKS)) == ("20k", "9d", 29)


def test_rank_label_and_targets():
    """A rank is shown in Japanese, and has a goal and a limit for each size of loss."""
    assert (rank_label("18k"), rank_label("3d"), rank_label("x")) == ("18級", "3段", "")
    assert targets_for("18級") == {20: (0, 1), 12: (1, 3), 10: (1, 5), 8: (2, 7), 6: (5, 11), 3: (11, 23)}
    assert targets_for("") is None
