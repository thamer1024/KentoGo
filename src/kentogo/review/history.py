"""Use the history database without stopping the quiz on errors.

save() is called once for each answer, when its result is known: at once when
the loss is in the SGF file, when KataGo has calculated it (even if the user
has already gone to the next problem), or when it cannot be judged. A copy of
the problem (as text) is saved with the answer, so that a problem in review
can still be asked when it is no longer made from its game (saved_problem_data).
This module knows only records and texts; kentogo.answers turns quiz sessions
and problems into them.

Saving the history must not stop the quiz. If the database cannot be written,
the error is printed and kept in last_error, and the quiz goes on.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from kentogo.review.record import AnswerRecord
from kentogo.review.store import ReviewStore


class AnswerHistory:
    """The history database, used without stopping the quiz on errors.

    Attributes:
        store: The history database.
        last_error: The last error of the database, or "" if there was none.
    """

    def __init__(self, store: ReviewStore, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        """Use a history database.

        Args:
            store: The history database.
            now: A function that returns the current time. Tests pass a fixed time.
        """
        self.store = store
        self.last_error = ""
        self._now = now

    def previous(self, problem_id: str) -> list[AnswerRecord]:
        """Return the earlier answers to a problem, the oldest first (empty if the database has an error)."""
        try:
            return self.store.answers(problem_id)
        except sqlite3.Error as error:
            self._report(error)
            return []

    def all_previous(self) -> dict[str, list[AnswerRecord]]:
        """Return all earlier answers, as a dict from problem ID to its answers (empty if the database has an error)."""
        try:
            return self.store.all_answers()
        except sqlite3.Error as error:
            self._report(error)
            return {}

    def exclusions(self) -> set[str]:
        """Return the IDs of the problems that are set aside (empty if the database has an error)."""
        try:
            return self.store.exclusions()
        except sqlite3.Error as error:
            self._report(error)
            return set()

    def last_reset(self) -> int:
        """Return the record_id of the last answer before the last reset (0 if none, or if the database has an error)."""
        try:
            return self.store.last_reset()
        except sqlite3.Error as error:
            self._report(error)
            return 0

    def now(self) -> datetime:
        """Return the current time, used as the time of a saved answer."""
        return self._now()

    def save(self, record: AnswerRecord, problem_data: str | None = None) -> None:
        """Save an answer when its result is known, with a copy of its problem.

        Args:
            record: The answer.
            problem_data: The problem as text (JSON), kept so that the problem can be asked
                again when it is no longer made from its game. None to keep no copy.
        """
        try:
            self.store.add_answer(record, problem_data)
        except sqlite3.Error as error:
            self._report(error)

    def saved_problem_data(self, problem_ids: list[str]) -> dict[str, str]:
        """Return the kept copies of problems as texts, by problem ID (empty if the database has an error)."""
        try:
            return self.store.problem_data(problem_ids)
        except sqlite3.Error as error:
            self._report(error)
            return {}

    def _report(self, error: sqlite3.Error) -> None:
        """Keep and print an error of the database."""
        self.last_error = str(error)
        print(f"cannot use the history: {error}", file=sys.stderr)
