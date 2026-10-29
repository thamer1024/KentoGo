"""The history of answers, kept in an SQLite database (Python's sqlite3).

The database has these tables:

- answers: one row for each answer.
- exclusions: problems that the user has set aside ("treat all current problems
  as done"). They are not asked.
- resets: when the user asked to start all problems again, and the last answer
  before it. Answers before the last reset are kept, but are not used to decide
  which problems to ask.
- problems: a copy of each answered problem (as JSON), so that a problem in
  review can still be asked when it is no longer made from its game (for
  example after the game is analyzed again, or the file is deleted).
- schema_version: the version of the tables, so that they can be changed later.
  Version 2 added exclusions and resets, and version 3 added problems; an older
  file gets the new tables when it is opened.

An answer is saved once, when its result is known: at once when its loss is in
the SGF file, or when KataGo has calculated it, or when it cannot be judged.
Each answer is written to the file at once (committed), so it is kept even if
the app stops later.

Do not open the same database from two computers at the same time (for example
in a cloud folder): the file may be broken.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kentogo.review.record import AnswerRecord

SCHEMA_VERSION = 3

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS answers (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    sgf_path TEXT NOT NULL,
    move_number INTEGER NOT NULL,
    color TEXT NOT NULL,
    answer TEXT NOT NULL,
    actual_move TEXT NOT NULL,
    best_move TEXT NOT NULL,
    answer_loss REAL,
    actual_loss REAL,
    loss_source TEXT NOT NULL,
    max_visits INTEGER,
    correct INTEGER,
    symmetry INTEGER NOT NULL,
    swap_colors INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS answers_by_problem ON answers (problem_id, record_id);
CREATE TABLE IF NOT EXISTS exclusions (problem_id TEXT PRIMARY KEY, excluded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resets (reset_at TEXT NOT NULL, last_record_id INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS problems (problem_id TEXT PRIMARY KEY, data TEXT NOT NULL);
"""

# The columns of the answers table, in the order of AnswerRecord (without record_id).
_COLUMNS = (
    "problem_id",
    "answered_at",
    "sgf_path",
    "move_number",
    "color",
    "answer",
    "actual_move",
    "best_move",
    "answer_loss",
    "actual_loss",
    "loss_source",
    "max_visits",
    "correct",
    "symmetry",
    "swap_colors",
)


class ReviewStore:
    """The history of answers in an SQLite file.

    Attributes:
        path: Path of the database file.
    """

    def __init__(self, path: str | Path):
        """Open the database, and make the tables if they do not exist.

        Args:
            path: Path of the database file. Its folder is made if needed.
                ":memory:" makes a database that is not saved (for tests).

        Raises:
            sqlite3.Error: If the file cannot be opened or is not a database.
            ValueError: If the file was made by a newer version of KentoGo.
        """
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        try:
            self._prepare()
        except BaseException:
            self._connection.close()
            raise

    def _prepare(self) -> None:
        """Make the tables, and check the version of a database that already has them."""
        with self._connection:
            self._connection.executescript(_CREATE_TABLES)
            row = self._connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._connection.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            elif row[0] > SCHEMA_VERSION:
                raise ValueError(f"{self.path} was made by a newer version of KentoGo (version {row[0]})")
            elif row[0] < SCHEMA_VERSION:
                # The new tables were made above; only the version number is left to change.
                self._connection.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

    def add_answer(self, record: AnswerRecord, problem_data: str | None = None) -> int:
        """Save an answer, and a copy of its problem, together (both or neither are written).

        Args:
            record: The answer. Its record_id is not used.
            problem_data: The problem as a JSON text (see quiz.problem_json), or None to keep no copy.
                A newer copy replaces the older one.

        Returns:
            The record_id of the saved answer.
        """
        values = [getattr(record, column) for column in _COLUMNS]
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connection:
            cursor = self._connection.execute(
                f"INSERT INTO answers ({', '.join(_COLUMNS)}) VALUES ({placeholders})", values
            )
            if problem_data is not None:
                self._connection.execute(
                    "INSERT OR REPLACE INTO problems (problem_id, data) VALUES (?, ?)",
                    (record.problem_id, problem_data),
                )
        return cursor.lastrowid

    def problem_data(self, problem_ids: list[str]) -> dict[str, str]:
        """Return the kept copies of problems, as a dict from problem ID to JSON text.

        IDs without a copy (for example answers saved by an older version) are left out.
        """
        found: dict[str, str] = {}
        for problem_id in problem_ids:
            row = self._connection.execute("SELECT data FROM problems WHERE problem_id = ?", (problem_id,)).fetchone()
            if row is not None:
                found[problem_id] = row[0]
        return found

    def answers(self, problem_id: str) -> list[AnswerRecord]:
        """Return all answers to a problem, the oldest first."""
        rows = self._connection.execute(
            f"SELECT {', '.join(_COLUMNS)}, record_id FROM answers WHERE problem_id = ? ORDER BY record_id",
            (problem_id,),
        ).fetchall()
        return [_record_from_row(row) for row in rows]

    def all_answers(self) -> dict[str, list[AnswerRecord]]:
        """Return all answers in one query, as a dict from problem ID to its answers (the oldest first).

        This is much faster than calling answers() for each of many problems.
        """
        rows = self._connection.execute(
            f"SELECT {', '.join(_COLUMNS)}, record_id FROM answers ORDER BY problem_id, record_id"
        ).fetchall()
        answers: dict[str, list[AnswerRecord]] = {}
        for row in rows:
            record = _record_from_row(row)
            answers.setdefault(record.problem_id, []).append(record)
        return answers

    def exclude(self, problem_ids: list[str], excluded_at: str) -> None:
        """Set problems aside, so that they are not asked (written at once).

        Args:
            problem_ids: The IDs of the problems.
            excluded_at: The time, in ISO 8601 format with the time zone.
        """
        with self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO exclusions (problem_id, excluded_at) VALUES (?, ?)",
                [(problem_id, excluded_at) for problem_id in problem_ids],
            )

    def exclusions(self) -> set[str]:
        """Return the IDs of the problems that are set aside."""
        return {row[0] for row in self._connection.execute("SELECT problem_id FROM exclusions")}

    def reset(self, reset_at: str) -> None:
        """Start all problems again: remove the exclusions, and remember the time (written at once).

        Answers are not deleted. Answers before the last reset are not used to choose problems.

        Args:
            reset_at: The time, in ISO 8601 format with the time zone.
        """
        with self._connection:
            last = self._connection.execute("SELECT COALESCE(MAX(record_id), 0) FROM answers").fetchone()[0]
            self._connection.execute("DELETE FROM exclusions")
            self._connection.execute("INSERT INTO resets (reset_at, last_record_id) VALUES (?, ?)", (reset_at, last))

    def last_reset(self) -> int:
        """Return the record_id of the last answer before the last reset (0 if there was no reset).

        Answers with a larger record_id were given after the reset. The record_id is used
        instead of the time, because it never goes back (the clock of a computer can).
        """
        return self._connection.execute("SELECT COALESCE(MAX(last_record_id), 0) FROM resets").fetchone()[0]

    def close(self) -> None:
        """Close the database."""
        self._connection.close()


def _record_from_row(row: tuple) -> AnswerRecord:
    """Make a record from a row of the answers table (the columns of _COLUMNS, then record_id)."""
    values = dict(zip((*_COLUMNS, "record_id"), row, strict=True))
    values["correct"] = None if values["correct"] is None else bool(values["correct"])
    values["swap_colors"] = bool(values["swap_colors"])
    return AnswerRecord(**values)
