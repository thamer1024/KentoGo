"""Open the history of answers and the problem cache, which are kept next to the settings file."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from kentogo.notice import Notice
from kentogo.quiz.problem_cache import ProblemCache
from kentogo.review.history import AnswerHistory
from kentogo.review.store import ReviewStore

# The names of the history database and the problem cache, kept in the same folder as the settings file.
HISTORY_FILE_NAME = "history.sqlite3"
CACHE_FILE_NAME = "problem_cache.sqlite3"


def open_cache(settings_path: Path, notices: list[Notice] | None = None) -> ProblemCache | None:
    """Open the problem cache in the folder of the settings file.

    Args:
        settings_path: Path of the settings file. "~" means the home folder.
        notices: If given, a message for the user is added when the cache cannot be used.

    Returns:
        The cache, or None if it cannot be used (the reason is printed).
        Then all SGF files are read, which is slower but works.
    """
    path = settings_path.expanduser().parent / CACHE_FILE_NAME
    try:
        return ProblemCache(path)
    except (sqlite3.Error, OSError) as error:
        print(f"cannot use the problem cache {path}: {error}", file=sys.stderr)
        if notices is not None:
            notices.append(Notice("notice_cache_failed", {"path": path, "reason": error}))
        return None


def open_history(settings_path: Path, notices: list[Notice] | None = None) -> AnswerHistory | None:
    """Open the history database in the folder of the settings file.

    Args:
        settings_path: Path of the settings file. "~" means the home folder.
        notices: If given, a message for the user is added when the history cannot be used.

    Returns:
        The history, or None if the database cannot be used (the reason is printed).
        The quiz works without the history.
    """
    return open_answers(settings_path.expanduser().parent / HISTORY_FILE_NAME, notices)


def open_answers(path: Path, notices: list[Notice] | None = None) -> AnswerHistory | None:
    """Open a history database of answers (see open_history), or None if it cannot be used (the reason is printed)."""
    try:
        return AnswerHistory(ReviewStore(path))
    except (sqlite3.Error, OSError, ValueError) as error:
        print(f"cannot use the history {path}: {error}", file=sys.stderr)
        if notices is not None:
            notices.append(Notice("notice_history_failed", {"path": path, "reason": error}))
        return None
