"""Tests for kentogo.seichi.seichi_plan."""

import random
from datetime import date, datetime

from kentogo.seichi.seichi_history import SeichiRecord, open_seichi_history
from kentogo.seichi.seichi_plan import plan_games, queue_from_history, start_queue
from kentogo.seichi.seichi_settings import ORDER_FILE_NAME, ORDER_NEWEST, SeichiSettings

COUNTED = "(;SZ[9]RE[B+1.5];B[ee];W[cc];B[];W[])"
RESIGNED = "(;SZ[9]RE[W+R];B[ee])"


def folder_with(tmp_path, files: dict[str, str]):
    """Write SGF files into a folder."""
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def result(name: str, day: str, correct: bool) -> SeichiRecord:
    """A result of a game on a day."""
    return SeichiRecord(name, f"{day}T12:00:00+09:00", name, correct)


def test_order_by_file_name_and_newest(tmp_path):
    """The games follow the order of the settings."""
    folder = folder_with(tmp_path, {"a.sgf": COUNTED, "b.sgf": COUNTED, "c.sgf": COUNTED})
    by_name = plan_games(folder, SeichiSettings(order=ORDER_FILE_NAME), {}, date(2026, 10, 22))
    assert [file.problem_id for file in by_name] == ["a.sgf", "b.sgf", "c.sgf"]
    times = {"a.sgf": 1.0, "b.sgf": 3.0, "c.sgf": 2.0}
    newest = plan_games(
        folder, SeichiSettings(order=ORDER_NEWEST), {}, date(2026, 10, 22), modified_time=lambda p: times[p.name]
    )
    assert [file.problem_id for file in newest] == ["b.sgf", "c.sgf", "a.sgf"]


def test_games_counted_well_are_not_asked_and_due_ones_come_first(tmp_path):
    """A game counted well is done; a game counted badly yesterday is asked again, first when reviews come first."""
    folder = folder_with(tmp_path, {"a.sgf": COUNTED, "b.sgf": COUNTED, "c.sgf": COUNTED})
    results = {"a.sgf": [result("a.sgf", "2026-10-21", True)], "c.sgf": [result("c.sgf", "2026-10-21", False)]}
    settings = SeichiSettings(order=ORDER_FILE_NAME, priority="review_first")
    files = plan_games(folder, settings, results, date(2026, 10, 22))
    assert [(file.problem_id, file.review) for file in files] == [("c.sgf", True), ("b.sgf", False)]


def test_the_queue_skips_resigned_games_and_stops_at_the_limit(tmp_path):
    """Games that did not end by counting are skipped; after the limit, no game is given."""
    folder = folder_with(tmp_path, {"a.sgf": RESIGNED, "b.sgf": COUNTED, "c.sgf": COUNTED})
    queue = start_queue(folder, SeichiSettings(order=ORDER_FILE_NAME, session_limit=1), {}, date(2026, 10, 22))
    game = queue.next_game()
    assert game.problem_id == "b.sgf" and not game.review
    queue.count_one()
    assert queue.finished and queue.next_game() is None


def test_random_order_and_no_limit(tmp_path):
    """With the random order, every game can come first; 0 means no limit."""
    folder = folder_with(tmp_path, {"a.sgf": COUNTED, "b.sgf": COUNTED})
    firsts = {
        start_queue(folder, SeichiSettings(), {}, date(2026, 10, 22), random.Random(seed)).next_game().problem_id
        for seed in range(20)
    }
    assert firsts == {"a.sgf", "b.sgf"}
    assert start_queue(folder, SeichiSettings(session_limit=0), {}, date(2026, 10, 22)).limit is None


def test_games_counted_earlier_today_count_toward_the_daily_limit(tmp_path):
    """A game counted earlier today counts; one counted yesterday does not. With the limit off, there is none."""
    folder = folder_with(tmp_path, {"a.sgf": COUNTED, "b.sgf": COUNTED})
    today = date(2026, 10, 22)
    earlier = datetime(2026, 10, 22, 9, 0).astimezone().isoformat()
    yesterday = datetime(2026, 10, 21, 23, 0).astimezone().isoformat()
    results = {"x.sgf": [SeichiRecord("x.sgf", yesterday, "x", True), SeichiRecord("x.sgf", earlier, "x", True)]}
    queue = start_queue(folder, SeichiSettings(session_limit=1), results, today)
    assert queue.finished and queue.today_count == 1 and queue.next_game() is None
    queue = start_queue(folder, SeichiSettings(session_limit=2), results, today)
    assert not queue.finished and queue.next_game() is not None
    assert start_queue(folder, SeichiSettings(session_limit=1, daily_limit_off=True), results, today).limit is None


def test_the_queue_is_planned_from_the_history(tmp_path):
    """The results in the history decide the plan; without a history, every game is new."""
    (tmp_path / "games").mkdir()
    folder = folder_with(tmp_path / "games", {"a.sgf": COUNTED})
    history, problem = open_seichi_history(tmp_path / "settings.json")
    assert problem == ""
    history.save("a.sgf", str(folder / "a.sgf"), True)
    today = datetime.now().astimezone().date()
    assert queue_from_history(folder, SeichiSettings(), history, today).next_game() is None  # Counted well: done.
    assert queue_from_history(folder, SeichiSettings(), None, today).next_game().problem_id == "a.sgf"
    history.close()


def test_a_game_counted_badly_is_asked_the_next_day_not_the_same_day(tmp_path):
    """A game counted badly is not asked again the same day; the next day it is a review again."""
    folder = folder_with(tmp_path, {"a.sgf": COUNTED})
    results = {"a.sgf": [result("a.sgf", "2026-10-22", False)]}
    settings = SeichiSettings(order=ORDER_FILE_NAME)
    assert plan_games(folder, settings, results, date(2026, 10, 22)) == []
    files = plan_games(folder, settings, results, date(2026, 10, 23))
    assert [(file.problem_id, file.review) for file in files] == [("a.sgf", True)]


def test_two_good_counts_in_a_row_finish_a_game_by_default(tmp_path):
    """By default, a game counted well twice in a row is not asked again."""
    folder = folder_with(tmp_path, {"a.sgf": COUNTED})
    once = {"a.sgf": [result("a.sgf", "2026-10-20", True)]}
    assert [file.problem_id for file in plan_games(folder, SeichiSettings(), once, date(2026, 10, 23))] == ["a.sgf"]
    twice = {"a.sgf": [*once["a.sgf"], result("a.sgf", "2026-10-23", True)]}
    assert plan_games(folder, SeichiSettings(), twice, date(2026, 12, 31)) == []
