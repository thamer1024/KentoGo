"""Tests for kentogo.clear_history."""

import random
from datetime import datetime

from test_today import answer_first_problem, three_games

from kentogo.app_settings import AppSettings
from kentogo.clear_history import BACKUP_FOLDER_NAME, clear_answers, clear_fight_answers, clear_seichi_results
from kentogo.fights_today import fight_history_path
from kentogo.review.history import AnswerHistory
from kentogo.review.record import AnswerRecord
from kentogo.review.store import ReviewStore
from kentogo.seichi.seichi_history import SeichiHistory, open_seichi_history
from kentogo.today import load_today, open_history

NOW = datetime(2026, 11, 13, 15, 50, 7)


def test_clear_answers_keeps_a_dated_backup(tmp_path):
    """Clearing asks all problems as new again, and the old answers are kept in a backup named by the time."""
    games = three_games(tmp_path)
    settings_path = tmp_path / "settings.json"
    history = open_history(settings_path)
    answer_first_problem(history, games, "Q4")  # Correct: done.
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 2

    backup = clear_answers(settings_path, NOW)
    assert backup == tmp_path / BACKUP_FOLDER_NAME / "history-20261113-155007.sqlite3"
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 3
    assert history.all_previous() == {}  # The history that the app keeps open sees the cleared file.
    kept = ReviewStore(backup)
    assert len(kept.all_answers()) == 1
    kept.close()
    history.store.close()


def test_clear_seichi_results_keeps_a_dated_backup(tmp_path):
    """The results of the practice are cleared, also for the history that the app keeps open, after a backup."""
    settings_path = tmp_path / "settings.json"
    history, _problem = open_seichi_history(settings_path)
    history.save("a.sgf", "/games/a.sgf", True)

    backup = clear_seichi_results(settings_path, NOW)
    assert backup == tmp_path / BACKUP_FOLDER_NAME / "seichi_history-20261113-155007.sqlite3"
    assert history.all_results() == {}
    history.close()
    kept = SeichiHistory(backup)
    assert list(kept.all_results()) == ["a.sgf"]
    kept.close()


def test_clear_fight_answers_keeps_a_dated_backup(tmp_path):
    """The local fights' history is cleared on its own (the quiz's history is kept), after a backup."""
    settings_path = tmp_path / "settings.json"
    quiz_history = open_history(settings_path)
    fights = AnswerHistory(ReviewStore(fight_history_path(settings_path)))
    for history in (quiz_history, fights):
        history.save(
            AnswerRecord("p", NOW.isoformat(), "a.sgf", 3, "B", "A1", "B1", "", None, None, "", None, False, 0, False)
        )
    backup = clear_fight_answers(settings_path, NOW)
    assert backup == tmp_path / BACKUP_FOLDER_NAME / "fight_history-20261113-155007.sqlite3"
    assert fights.all_previous() == {} and len(quiz_history.all_previous()["p"]) == 1
    kept = ReviewStore(backup)
    assert len(kept.all_answers()) == 1
    for store in (kept, fights.store, quiz_history.store):
        store.close()
