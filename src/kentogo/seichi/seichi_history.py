"""The results of the territory counting practice, kept in an SQLite database (Python's sqlite3).

After counting a game, the user says whether it went well ("できた") or not. Each
result is one row, written to the file at once. The results decide which games are
asked again, in the same way as the answers of the quiz (see repetition.schedule): a game
is known by the name of its SGF file.

Using the database must not stop the practice: when it cannot be read or written,
the error is kept in last_error (and printed), and the practice goes on.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FILE_NAME = "seichi_history.sqlite3"

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS results (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    sgf_path TEXT NOT NULL,
    correct INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS results_by_game ON results (problem_id, record_id);
"""


@dataclass(frozen=True)
class SeichiRecord:
    """One counted game. It has what repetition.schedule.review_state reads from an answer.

    Attributes:
        problem_id: The game: the name of its SGF file.
        answered_at: When the result was saved, in ISO 8601 format with the time zone.
        sgf_path: The SGF file, for reference.
        correct: True if the user counted it well.
    """

    problem_id: str
    answered_at: str
    sgf_path: str
    correct: bool


class SeichiHistory:
    """The results of the territory counting practice.

    Attributes:
        path: The database file.
        last_error: The last error of the database, or "" if there was none.
    """

    def __init__(self, path: Path, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        """Open (or make) the database.

        Args:
            path: The database file.
            now: A function that returns the current time. Tests pass a fixed time.

        Raises:
            sqlite3.Error: If the database cannot be opened.
        """
        self.path = path
        self.last_error = ""
        self._now = now
        path.parent.mkdir(parents=True, exist_ok=True)
        # The games are chosen in a background thread, and the results saved in the main thread (never at once).
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.executescript(_CREATE_TABLES)
        self._connection.commit()

    def save(self, problem_id: str, sgf_path: str, correct: bool) -> None:
        """Save the result of one counted game (an error is kept in last_error)."""
        answered_at = self._now().astimezone().isoformat()
        try:
            self._connection.execute(
                "INSERT INTO results (problem_id, answered_at, sgf_path, correct) VALUES (?, ?, ?, ?)",
                (problem_id, answered_at, sgf_path, int(correct)),
            )
            self._connection.commit()
        except sqlite3.Error as error:
            self._report(error)

    def all_results(self) -> dict[str, list[SeichiRecord]]:
        """Return all results, as a dict from the game to its results, the oldest first (empty on an error)."""
        try:
            rows = self._connection.execute(
                "SELECT problem_id, answered_at, sgf_path, correct FROM results ORDER BY record_id"
            ).fetchall()
        except sqlite3.Error as error:
            self._report(error)
            return {}
        results: dict[str, list[SeichiRecord]] = {}
        for problem_id, answered_at, sgf_path, correct in rows:
            results.setdefault(problem_id, []).append(SeichiRecord(problem_id, answered_at, sgf_path, bool(correct)))
        return results

    def close(self) -> None:
        """Close the database."""
        self._connection.close()

    def _report(self, error: sqlite3.Error) -> None:
        """Keep and print an error of the database."""
        self.last_error = str(error)
        print(f"seichi history {self.path}: {error}", file=sys.stderr)


def open_seichi_history(settings_path: Path) -> tuple[SeichiHistory | None, str]:
    """Open the database in the folder of the settings file.

    Returns:
        The history and "", or None and the reason when it cannot be used (the practice works without it).
    """
    path = settings_path.expanduser().parent / FILE_NAME
    try:
        return SeichiHistory(path), ""
    except (sqlite3.Error, OSError) as error:
        print(f"cannot use the seichi history {path}: {error}", file=sys.stderr)
        return None, f"{path}: {error}"
