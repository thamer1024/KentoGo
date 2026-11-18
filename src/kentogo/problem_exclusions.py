"""Set all the problems aside, or start them all again (from the settings screen).

exclude_all_problems ("treat all current problems as done") and include_all_problems ("start
all problems again") write to the history at once, and are used from the next start.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kentogo.commentary_inputs import read_recorded_colors
from kentogo.games_folder import find_games_folder
from kentogo.notice import Notice
from kentogo.practice_stores import HISTORY_FILE_NAME, open_cache
from kentogo.quiz.collect import collect_games
from kentogo.quiz.problem_kinds import problems_of_kind
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.review.store import ReviewStore


class NoGamesFolderError(ValueError):
    """Raised when there is no games folder to read.

    Attributes:
        notice: Why (see find_games_folder).
    """

    def __init__(self, notice: Notice):
        """Keep why there is no folder."""
        super().__init__(f"no games folder: {notice.values}")
        self.notice = notice


def exclude_all_problems(settings_path: Path, folder_argument: Path | None, settings: QuizSettings) -> int:
    """Set aside every problem in the games folder now, as if all were done (written at once).

    Problems from games added later are not set aside. This uses its own
    connections, so it can run in a background thread.

    Args:
        settings_path: Path of the settings file (the cache and the history are next to it).
        folder_argument: The games folder given on the command line, or None.
        settings: The quiz settings (the games folder and the conditions for choosing problems).

    Returns:
        How many problems were set aside.

    Raises:
        NoGamesFolderError: If there is no games folder (its notice tells why).
        ValueError: If the history is newer.
        sqlite3.Error, OSError: If the history cannot be written.
    """
    folder, folder_problem = find_games_folder(folder_argument, settings.games_folder)
    if folder is None:
        raise NoGamesFolderError(folder_problem)
    cache = open_cache(settings_path)
    try:
        games, _ = collect_games(folder, settings.extract, cache, recorded_colors=read_recorded_colors(settings_path))
        problems = problems_of_kind((result for _path, result in games), settings.problem_kind)
    finally:
        if cache is not None:
            cache.close()
    problem_ids = sorted({problem.problem_id for problem in problems})
    store = ReviewStore(settings_path.expanduser().parent / HISTORY_FILE_NAME)
    try:
        store.exclude(problem_ids, _now())
    finally:
        store.close()
    return len(problem_ids)


def include_all_problems(settings_path: Path) -> None:
    """Start all problems again: no problem is set aside or done (written at once).

    The answers are kept, but answers before now are not used to choose problems.

    Args:
        settings_path: Path of the settings file (the history is next to it).

    Raises:
        ValueError: If the history was made by a newer version.
        sqlite3.Error, OSError: If the history cannot be written.
    """
    store = ReviewStore(settings_path.expanduser().parent / HISTORY_FILE_NAME)
    try:
        store.reset(_now())
    finally:
        store.close()


def _now() -> str:
    """Return the current time in ISO 8601 format with the time zone, as in the history."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
