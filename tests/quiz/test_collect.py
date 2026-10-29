"""Tests for kentogo.quiz.collect, and for the problem cache that it uses."""

import os
import sqlite3

import pytest

from kentogo.mistakes.extract import ExtractSettings
from kentogo.quiz import collect
from kentogo.quiz.collect import collect_problems
from kentogo.quiz.problem_cache import ProblemCache
from kentogo.record.katrain_comment import INTERNAL_MARKER

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def sgf_with_mistake(loss: float) -> str:
    """Make a game where black's second move loses the given points."""
    comment = f"\nMove 3: B A19\nEstimated point loss: {loss:.1f}\nPV: BQ4\n" + INTERNAL_MARKER
    return f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd];W[dp];B[aa]C[{comment}])"


@pytest.fixture
def reads(monkeypatch):
    """Count how many SGF files are really read (not taken from the cache)."""
    counter = {"files": 0}
    real_load_game = collect.load_game

    def counting_load_game(path):
        counter["files"] += 1
        return real_load_game(path)

    monkeypatch.setattr(collect, "load_game", counting_load_game)
    return counter


def test_unchanged_files_come_from_the_cache(tmp_path, reads):
    """At the second start, unchanged files are not read, and the problems are the same."""
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    (tmp_path / "b.sgf").write_text(sgf_with_mistake(4.0), encoding="utf-8")
    cache_path = tmp_path / "cache" / "problem_cache.sqlite3"

    cache = ProblemCache(cache_path)
    first = collect_problems(tmp_path, ExtractSettings(), cache)
    cache.close()
    assert reads["files"] == 2

    cache = ProblemCache(cache_path)
    second = collect_problems(tmp_path, ExtractSettings(), cache)
    cache.close()
    assert reads["files"] == 2  # Nothing was read again.
    assert second == first


def test_changed_file_is_read_again(tmp_path, reads):
    """A file that has changed is read again, and its new problems are used."""
    game = tmp_path / "a.sgf"
    game.write_text(sgf_with_mistake(9.0), encoding="utf-8")
    cache = ProblemCache(":memory:")
    collect_problems(tmp_path, ExtractSettings(), cache)

    game.write_text(sgf_with_mistake(12.0), encoding="utf-8")
    os.utime(game, ns=(1, 1))  # Make sure the time of change is different.
    problems, _ = collect_problems(tmp_path, ExtractSettings(), cache)
    assert reads["files"] == 2
    assert problems[0].points_lost == 12.0


def test_changed_settings_read_the_files_again(tmp_path, reads):
    """When the settings change, the files are read again with the new settings."""
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    cache = ProblemCache(":memory:")
    collect_problems(tmp_path, ExtractSettings(), cache)
    problems, _ = collect_problems(tmp_path, ExtractSettings(min_points_lost=10.0), cache)
    assert reads["files"] == 2
    assert problems == []


def test_broken_and_skipped_files_are_reported_from_the_cache(tmp_path, reads):
    """Broken and skipped files are reported the same way when they come from the cache."""
    (tmp_path / "b.sgf").write_text("(;SZ[19]PB[x]PW[y];B[pd])", encoding="utf-8")
    (tmp_path / "c.sgf").write_text(f"(;SZ[9:13]PB[{HUMAN}]PW[{AI}];B[aa])", encoding="utf-8")
    cache = ProblemCache(":memory:")
    first = collect_problems(tmp_path, ExtractSettings(), cache)
    second = collect_problems(tmp_path, ExtractSettings(), cache)
    assert reads["files"] == 2
    assert second == first
    assert first[1][0].message() == "b.sgf: skipped (unknown_color)"
    assert first[1][1].message().startswith("c.sgf: cannot read")


def test_deleted_files_are_forgotten(tmp_path):
    """Files that are no longer in the folder are removed from the cache."""
    game = tmp_path / "a.sgf"
    game.write_text(sgf_with_mistake(9.0), encoding="utf-8")
    cache = ProblemCache(":memory:")
    collect_problems(tmp_path, ExtractSettings(), cache)
    game.unlink()
    assert collect_problems(tmp_path, ExtractSettings(), cache) == ([], [])
    assert cache._connection.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0


def test_without_cache(tmp_path, reads):
    """Without a cache, every file is read every time."""
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    collect_problems(tmp_path, ExtractSettings())
    collect_problems(tmp_path, ExtractSettings())
    assert reads["files"] == 2


def test_broken_cache_file_is_refused(tmp_path):
    """A cache file that is not a database cannot be opened (the app then reads all files)."""
    path = tmp_path / "problem_cache.sqlite3"
    path.write_text("not a database")
    with pytest.raises(sqlite3.Error):
        ProblemCache(path)


def test_game_without_analysis_is_reported(tmp_path):
    """A game with the user's color but without KaTrain's comments or analysis data is reported."""
    (tmp_path / "plain.sgf").write_text(f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd];W[dp])", encoding="utf-8")
    problems, skipped = collect_problems(tmp_path, ExtractSettings())
    assert problems == []
    assert [(game.name, game.reason) for game in skipped] == [("plain.sgf", "no_analysis")]


def test_recorded_color_is_used_and_reads_the_file_again(tmp_path, reads):
    """A color given by the user finds the color of a game with two humans, even if the file was in the cache."""
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0).replace(f"PW[{AI}]", f"PW[{HUMAN}]"), encoding="utf-8")
    cache = ProblemCache(":memory:")
    problems, skipped = collect_problems(tmp_path, ExtractSettings(), cache)
    assert problems == [] and [game.reason for game in skipped] == ["unknown_color"]

    problems, skipped = collect_problems(tmp_path, ExtractSettings(), cache, recorded_colors={"a.sgf": "B"})
    assert reads["files"] == 2  # Read again, because the recorded color has changed.
    assert [problem.points_lost for problem in problems] == [9.0] and skipped == []
