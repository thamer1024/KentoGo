"""Tests for kentogo.review.store."""

import sqlite3
from dataclasses import replace

import pytest

from kentogo.review.record import LOSS_UNKNOWN, AnswerRecord
from kentogo.review.store import SCHEMA_VERSION, ReviewStore

RECORD = AnswerRecord(
    problem_id="p1",
    answered_at="2026-10-20T21:30:00+09:00",
    sgf_path="/games/game.sgf",
    move_number=3,
    color="B",
    answer="R4",
    actual_move="A19",
    best_move="Q4",
    answer_loss=None,
    actual_loss=None,
    loss_source=LOSS_UNKNOWN,
    max_visits=None,
    correct=None,
    symmetry=3,
    swap_colors=True,
)


def test_answers_are_saved_and_read_back(tmp_path):
    """Saved answers are read back in order, also after the file is opened again."""
    path = tmp_path / "folder" / "history.sqlite3"
    store = ReviewStore(path)
    first = store.add_answer(RECORD)
    second = store.add_answer(replace(RECORD, answer="Q4", answer_loss=0.0, actual_loss=8.0, correct=False))
    store.add_answer(replace(RECORD, problem_id="p2"))
    store.close()

    store = ReviewStore(path)
    answers = store.answers("p1")
    store.close()
    assert [answer.record_id for answer in answers] == [first, second]
    assert answers[0] == replace(RECORD, record_id=first)
    assert (answers[1].answer, answers[1].correct) == ("Q4", False)


def test_no_answers():
    """A problem that was never answered has no answers."""
    assert ReviewStore(":memory:").answers("p1") == []


def test_newer_database_is_refused(tmp_path):
    """A database made by a newer version is not used, so that it is not broken."""
    path = tmp_path / "history.sqlite3"
    ReviewStore(path).close()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE schema_version SET version = 99")
    connection.close()
    with pytest.raises(ValueError):
        ReviewStore(path)


def test_broken_file_is_refused(tmp_path):
    """A file that is not a database raises sqlite3.Error."""
    path = tmp_path / "history.sqlite3"
    path.write_text("not a database")
    with pytest.raises(sqlite3.Error):
        ReviewStore(path)


def test_answers_are_written_at_once(tmp_path):
    """Each answer is written to the file at once, so it is kept even if the app stops without closing."""
    path = tmp_path / "history.sqlite3"
    store = ReviewStore(path)
    store.add_answer(replace(RECORD, answer_loss=1.0, actual_loss=9.0, correct=True))
    other = ReviewStore(path)  # Opened while the first one is still open, as another program would.
    [saved] = other.answers("p1")
    assert (saved.answer_loss, saved.correct) == (1.0, True)
    other.close()
    store.close()


def test_all_answers():
    """All answers are read at once, grouped by problem, the oldest first in each problem."""
    store = ReviewStore(":memory:")
    first = store.add_answer(RECORD)
    other = store.add_answer(replace(RECORD, problem_id="p0"))
    second = store.add_answer(replace(RECORD, answer="Q4"))
    answers = store.all_answers()
    assert {key: [record.record_id for record in records] for key, records in answers.items()} == {
        "p0": [other],
        "p1": [first, second],
    }


def test_exclusions_and_reset():
    """Problems can be set aside, and a reset brings them back and remembers the last answer before it."""
    store = ReviewStore(":memory:")
    assert (store.exclusions(), store.last_reset()) == (set(), 0)
    store.exclude(["p1", "p2"], "2026-10-20T10:00:00+09:00")
    store.exclude(["p2", "p3"], "2026-10-21T10:00:00+09:00")
    assert store.exclusions() == {"p1", "p2", "p3"}
    store.add_answer(RECORD)
    last = store.add_answer(RECORD)
    store.reset("2026-10-22T10:00:00+09:00")
    store.add_answer(RECORD)
    assert store.exclusions() == set()
    assert store.last_reset() == last


def test_version_1_file_is_upgraded(tmp_path):
    """A file made by version 1 gets the new tables, and keeps its answers."""
    path = tmp_path / "history.sqlite3"
    store = ReviewStore(path)
    store.add_answer(RECORD)
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE exclusions")
        connection.execute("DROP TABLE resets")
        connection.execute("UPDATE schema_version SET version = 1")
    connection.close()

    store = ReviewStore(path)
    assert len(store.answers("p1")) == 1
    store.exclude(["p1"], "2026-10-20T10:00:00+09:00")
    assert store.exclusions() == {"p1"}
    assert store._connection.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION
    store.close()


def test_problem_copies():
    """A copy of the problem is saved with the answer, and a newer copy replaces the older one."""
    store = ReviewStore(":memory:")
    store.add_answer(RECORD, '{"old": 1}')
    store.add_answer(RECORD, '{"new": 2}')
    store.add_answer(replace(RECORD, problem_id="p2"))  # No copy.
    assert store.problem_data(["p1", "p2", "p3"]) == {"p1": '{"new": 2}'}
