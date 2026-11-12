"""Clear a history of the practices, after copying it to a dated backup file (buttons of the settings screen).

The histories are SQLite files next to the settings file. Before one is cleared, the whole of it is copied with
SQLite's own backup into the folder BACKUP_FOLDER_NAME next to it, named by the date and time, such as
backups/history-20261113-155000.sqlite3; the backup can be put back by hand in place of the history. Only when
the copy is made is the history cleared, in the file (it is not removed), so that the app can go on using it.

- clear_answers: the answers of the quiz and its reviews. From the next start of the quiz, the problems are
  chosen as for a new user.
- clear_seichi_results: the results of the territory counting practice.

The other files are kept: the settings, the problem cache, and the history of the AI commentary (it has the
user's colors and ranks of games, which the quiz uses too).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kentogo.review.store import ReviewStore
from kentogo.seichi.seichi_history import FILE_NAME as SEICHI_FILE_NAME
from kentogo.seichi.seichi_history import SeichiHistory
from kentogo.today import HISTORY_FILE_NAME

BACKUP_FOLDER_NAME = "backups"  # Next to the histories.


def backup_path(history: Path, now: datetime) -> Path:
    """Return the path of a history's backup, named by the date and time, such as history-20261113-155000.sqlite3."""
    return history.parent / BACKUP_FOLDER_NAME / f"{history.stem}-{now:%Y%m%d-%H%M%S}{history.suffix}"


def clear_answers(settings_path: Path, now: datetime) -> Path:
    """Clear the history of answers of the quiz, after copying it to a backup file.

    Args:
        settings_path: Path of the settings file (the history is next to it).
        now: The local date and time, for the name of the backup.

    Returns:
        The path of the backup.

    Raises:
        ValueError: If the history was made by a newer version.
        sqlite3.Error, OSError: If the history cannot be copied or written (when it cannot be copied, it is kept).
    """
    path = settings_path.expanduser().parent / HISTORY_FILE_NAME
    backup = backup_path(path, now)
    store = ReviewStore(path)
    try:
        store.backup(backup)
        store.clear()
    finally:
        store.close()
    return backup


def clear_seichi_results(settings_path: Path, now: datetime) -> Path:
    """Clear the results of the territory counting practice, after copying them to a backup file.

    Args:
        settings_path: Path of the settings file (the results are next to it).
        now: The local date and time, for the name of the backup.

    Returns:
        The path of the backup.

    Raises:
        sqlite3.Error, OSError: If the results cannot be copied or written (when they cannot be copied, they are kept).
    """
    path = settings_path.expanduser().parent / SEICHI_FILE_NAME
    backup = backup_path(path, now)
    history = SeichiHistory(path)
    try:
        history.backup(backup)
        history.clear()
    finally:
        history.close()
    return backup
