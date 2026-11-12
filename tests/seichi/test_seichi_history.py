"""Tests for kentogo.seichi.seichi_history."""

from datetime import datetime, timezone

from kentogo.seichi.seichi_history import SeichiHistory, open_seichi_history


def test_results_are_kept_in_the_file(tmp_path):
    """Results are saved at once, and read back by game, the oldest first."""
    times = iter([datetime(2026, 10, 20, tzinfo=timezone.utc), datetime(2026, 10, 21, tzinfo=timezone.utc)])
    history = SeichiHistory(tmp_path / "s.sqlite3", now=lambda: next(times))
    history.save("a.sgf", "/games/a.sgf", False)
    history.save("a.sgf", "/games/a.sgf", True)
    history.close()
    again = SeichiHistory(tmp_path / "s.sqlite3")
    results = again.all_results()
    assert [record.correct for record in results["a.sgf"]] == [False, True]
    assert results["a.sgf"][0].answered_at < results["a.sgf"][1].answered_at
    assert again.last_error == ""


def test_open_next_to_the_settings(tmp_path):
    """The database is made in the folder of the settings file."""
    history, problem = open_seichi_history(tmp_path / "settings.json")
    assert history is not None and problem == "" and history.path.parent == tmp_path
    history.close()


def test_backup_then_clear(tmp_path):
    """The backup keeps the results; clearing leaves an empty history that still works."""
    history = SeichiHistory(tmp_path / "s.sqlite3")
    history.save("a.sgf", "/games/a.sgf", True)
    history.backup(tmp_path / "backups" / "s-1.sqlite3")
    history.clear()
    assert history.all_results() == {}
    history.save("b.sgf", "/games/b.sgf", False)
    assert list(history.all_results()) == ["b.sgf"]
    history.close()
    kept = SeichiHistory(tmp_path / "backups" / "s-1.sqlite3")
    assert list(kept.all_results()) == ["a.sgf"]
    kept.close()
