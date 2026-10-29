"""Tests for kentogo.commentary.history."""

import pytest

from kentogo.commentary.history import (
    STATE_DONE,
    STATE_EXCLUDED,
    STATE_PENDING,
    CommentaryHistory,
    GameEntry,
    history_path,
)


def test_inputs_are_kept_in_the_file(tmp_path):
    """The inputs of a game are written at once, and read back after opening again."""
    history = CommentaryHistory(tmp_path / "c.sqlite3")
    history.save_inputs("a.sgf", "W", "18k", "same")
    history.close()
    again = CommentaryHistory(tmp_path / "c.sqlite3")
    assert again.entry("a.sgf") == GameEntry("a.sgf", "W", "18k", "same")
    assert again.entry("b.sgf") is None
    again.close()


def test_states_keep_the_inputs():
    """Changing the state keeps the inputs, and changing the inputs keeps the state."""
    history = CommentaryHistory(":memory:")
    history.save_inputs("a.sgf", "B", "17k", "")
    history.mark_pending("a.sgf")
    assert history.entry("a.sgf") == GameEntry("a.sgf", "B", "17k", "", STATE_PENDING)
    history.mark_done("a.sgf", 123)
    history.save_inputs("a.sgf", "B", "16k", "")
    assert history.entry("a.sgf") == GameEntry("a.sgf", "B", "16k", "", STATE_DONE, 123)


def test_exclude_and_include():
    """An excluded game can be included again, and then has no state."""
    history = CommentaryHistory(":memory:")
    history.exclude("a.sgf")
    assert history.entry("a.sgf").state == STATE_EXCLUDED
    history.include("a.sgf")
    assert history.entry("a.sgf") == GameEntry("a.sgf")


def test_recorded_colors():
    """Only the games with a color given by the user are returned."""
    history = CommentaryHistory(":memory:")
    history.save_inputs("a.sgf", "W", "", "")
    history.save_inputs("b.sgf", "", "18k", "")
    history.mark_pending("c.sgf")
    assert history.recorded_colors() == {"a.sgf": "W"}
    assert set(history.all_entries()) == {"a.sgf", "b.sgf", "c.sgf"}


def test_wrong_color_is_refused():
    """A color other than B, W or empty is an error."""
    history = CommentaryHistory(":memory:")
    with pytest.raises(ValueError):
        history.save_inputs("a.sgf", "black", "", "")


def test_since():
    """The time from which changed games are shown is None at first, then the time that was set."""
    history = CommentaryHistory(":memory:")
    assert history.since_ns() is None
    history.set_since_ns(1_700_000_000_000_000_000)
    assert history.since_ns() == 1_700_000_000_000_000_000


def test_path_next_to_the_settings(tmp_path):
    """The database is in the folder of the settings file."""
    assert history_path(tmp_path / "settings.json") == tmp_path / "commentary_history.sqlite3"


def test_last_rank():
    """The last rank given for any game is kept; an empty rank does not change it."""
    history = CommentaryHistory(":memory:")
    assert history.last_rank() == ""
    history.save_inputs("a.sgf", "B", "18k", "")
    history.save_inputs("b.sgf", "W", "", "")
    assert history.last_rank() == "18k"
    history.save_inputs("c.sgf", "W", "17k", "")
    assert history.last_rank() == "17k"
