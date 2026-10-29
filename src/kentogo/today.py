"""Find today's problems: read the games (using the problem cache) and choose by the history.

The start screen calls load_today() in a background thread, and shows the
progress and then the numbers of new problems and reviews.

The settings screen calls exclude_all_problems() ("treat all current problems
as done") and include_all_problems() ("start all problems again"). They write
to the history at once, and are used from the next start.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path

from kentogo.answers import saved_problems
from kentogo.app_settings import AppSettings
from kentogo.commentary.history import CommentaryHistory
from kentogo.commentary.history import history_path as commentary_history_path
from kentogo.mistakes.problem import Problem
from kentogo.notice import Notice
from kentogo.quiz.collect import SkippedGame, collect_problems
from kentogo.quiz.order import keep_newest, order_problems
from kentogo.quiz.problem_cache import ProblemCache
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.repetition.daily import answered_on, left_today
from kentogo.repetition.modes import REVIEW_ONCE
from kentogo.repetition.plan import QuizPlan, plan_problems
from kentogo.repetition.schedule import ReviewState, review_state
from kentogo.review.history import AnswerHistory
from kentogo.review.review_settings import ReviewSettings
from kentogo.review.store import ReviewStore

# The names of the history database and the problem cache, kept in the same folder as the settings file.
HISTORY_FILE_NAME = "history.sqlite3"
CACHE_FILE_NAME = "problem_cache.sqlite3"

# The folder of the project when KentoGo runs from its source (for example, downloaded from GitHub).
PROJECT_FOLDER = Path(__file__).resolve().parents[2]
# The games folder when KentoGo is installed as a program (not from its source).
INSTALLED_GAMES_FOLDER = Path("~/.kentogo/games")

# A function that is told (files done, all files) while the SGF files are read.
Progress = Callable[[int, int], None]


class NoGamesFolderError(ValueError):
    """Raised when there is no games folder to read.

    Attributes:
        notice: Why (see find_games_folder).
    """

    def __init__(self, notice: Notice):
        """Keep why there is no folder."""
        super().__init__(f"no games folder: {notice.values}")
        self.notice = notice


@dataclass(frozen=True)
class TodayProblems:
    """Today's problems.

    Attributes:
        problems: The problems to ask, in order.
        message: Why there are no problems (None when there are problems).
        new_count: How many of them were never answered.
        review_count: How many of them are reviews.
        session_limit: How many more problems may be asked today, reviews included
            (None: no limit; see repetition.daily).
        skipped: How many games gave no problems, for each reason (see quiz.collect.SkippedGame).
        skipped_games: The games that gave no problems, to show the user which ones.
        notices: Problems to tell the user in a dialog (for example that the cache cannot be used).
    """

    problems: list[Problem]
    message: Notice | None = None
    new_count: int = 0
    review_count: int = 0
    session_limit: int | None = None
    skipped: dict[str, int] = field(default_factory=dict)
    skipped_games: list[SkippedGame] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)


def default_games_folder() -> Path:
    """Return the games folder used when the settings name none.

    From the source, it is the "games" folder of the project (empty at first, and kept out of
    git with the SGF files). An installed KentoGo uses "games" next to its settings instead.
    """
    if (PROJECT_FOLDER / "pyproject.toml").is_file():
        return PROJECT_FOLDER / "games"
    return INSTALLED_GAMES_FOLDER.expanduser()


def find_games_folder(
    argument: Path | None, setting: str, default: Path | None = None
) -> tuple[Path | None, Notice | None]:
    """Find the games folder: the one on the command line, or else the one in the settings, or else the default.

    The default folder is made if it does not exist yet. The app starts even without a
    usable folder, so that the user can set it on the settings screen.

    Args:
        argument: The folder given on the command line, or None.
        setting: The games_folder of the quiz settings ("" means the default folder).
        default: The default folder. None means default_games_folder() (tests give their own).

    Returns:
        A tuple (folder, problem). folder is None if there is no usable folder, and
        problem then tells why (None when there is a folder).
    """
    if argument is None and not setting.strip():
        folder = default or default_games_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None, Notice("folder_missing", {"folder": folder})
        return folder, None
    folder = argument or Path(setting.strip()).expanduser()
    if not folder.is_dir():
        return None, Notice("folder_missing", {"folder": folder})
    return folder, None


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
    path = settings_path.expanduser().parent / HISTORY_FILE_NAME
    try:
        return AnswerHistory(ReviewStore(path))
    except (sqlite3.Error, OSError, ValueError) as error:
        print(f"cannot use the history {path}: {error}", file=sys.stderr)
        if notices is not None:
            notices.append(Notice("notice_history_failed", {"path": path, "reason": error}))
        return None


def read_recorded_colors(settings_path: Path) -> dict[str, str]:
    """Read the user's colors given in the list of games for the AI commentary.

    Args:
        settings_path: Path of the settings file (the database is next to it).

    Returns:
        The color by the name of the SGF file, or an empty dict if the database
        cannot be read (the reason is printed; the colors are then found in other ways).
    """
    path = commentary_history_path(settings_path)
    if not path.exists():
        return {}
    try:
        history = CommentaryHistory(path)
        try:
            return history.recorded_colors()
        finally:
            history.close()
    except (sqlite3.Error, OSError) as error:
        print(f"cannot read the commentary history {path}: {error}", file=sys.stderr)
        return {}


def plan_today(
    problems: list[Problem], history: AnswerHistory, settings: ReviewSettings, today: date
) -> tuple[QuizPlan, int | None]:
    """Choose today's problems: new problems and the reviews that are due, in the order of the settings.

    Answers before the last reset are not used, and problems set aside are not asked.
    Reviews whose problems are no longer made from the games are asked from the
    copies kept in the history.

    Args:
        problems: All problems, in the order chosen in the settings.
        history: The history of answers.
        settings: The review settings (the review settings, the priority and the session limit).
        today: Today's date.

    Returns:
        A tuple (plan, limit). limit is how many more problems may be asked today, reviews
        included (see repetition.daily), or None if there is no limit.
    """
    answers = history.all_previous()  # One query for all problems, so that many problems stay fast.
    done = answered_on((record.answered_at for records in answers.values() for record in records), today)
    last_before_reset = history.last_reset()
    once = settings.review_mode == REVIEW_ONCE
    states = {}
    for problem_id in {problem.problem_id for problem in problems} | set(answers):
        records = [r for r in answers.get(problem_id, []) if r.record_id > last_before_reset]
        states[problem_id] = review_state(records, settings.review_streak, once)
    all_problems = problems + _lost_reviews(problems, states, history, today)
    limit = left_today(settings.daily_limit, done)
    plan = plan_problems(all_problems, states, today, settings.priority, history.exclusions(), limit)
    return plan, limit


def _lost_reviews(
    problems: list[Problem], states: dict[str, ReviewState], history: AnswerHistory, today: date
) -> list[Problem]:
    """Return the reviews due today whose problems are no longer made from the games.

    This happens when a game is analyzed again, the conditions for choosing problems
    change, or the file is moved or deleted. The copies kept in the history are used.
    """
    made = {problem.problem_id for problem in problems}
    lost = sorted(problem_id for problem_id, state in states.items() if problem_id not in made and state.is_due(today))
    return saved_problems(history, lost) if lost else []


def prepare_problems(
    folder_argument: Path | None,
    settings: AppSettings,
    history: AnswerHistory | None,
    rng: random.Random,
    cache: ProblemCache | None = None,
    progress: Progress | None = None,
    recorded_colors: Mapping[str, str] | None = None,
) -> TodayProblems:
    """Make the problems to ask today, and print what was found.

    Without a history, all problems are asked (it is not known which were answered).

    Args:
        folder_argument: The games folder given on the command line, or None.
        settings: All settings (the quiz and the review settings are used).
        history: The history of answers, or None if it cannot be used.
        rng: The random number generator, for the random order.
        cache: The problem cache, or None to read every SGF file.
        progress: Called with (files done, all files) while the SGF files are read.
        recorded_colors: The user's color that the user gave, by the name of the SGF file.

    Returns:
        Today's problems, or why there are none.
    """
    folder, folder_problem = find_games_folder(folder_argument, settings.quiz.games_folder)
    if folder is None:
        print(f"no games folder: {folder_problem.values}", file=sys.stderr)
        return TodayProblems([], folder_problem)
    problems, skipped = collect_problems(folder, settings.quiz.extract, cache, progress, recorded_colors)
    for game in skipped:
        print(game.message(), file=sys.stderr)
    skipped_counts = dict(Counter(game.reason for game in skipped))
    problems = order_problems(keep_newest(problems), settings.quiz.order, rng)
    if history is None:
        print(f"{len(problems)} problems (no history)", file=sys.stderr)
        return TodayProblems(problems, None, len(problems), 0, skipped=skipped_counts, skipped_games=skipped)
    plan, limit = plan_today(problems, history, settings.review, date.today())
    print(f"{len(problems)} problems: {plan.new_count} new, {plan.review_count} reviews today", file=sys.stderr)
    notices = [Notice("notice_history_error", {"reason": history.last_error})] if history.last_error else []
    if problems and not plan.problems:
        message = Notice("daily_done" if limit == 0 else "nothing_today")
        return TodayProblems(
            [], message, session_limit=limit, skipped=skipped_counts, skipped_games=skipped, notices=notices
        )
    return TodayProblems(
        plan.problems, None, plan.new_count, plan.review_count, limit, skipped_counts, skipped, notices
    )


def load_today(
    settings_path: Path,
    folder_argument: Path | None,
    settings: AppSettings,
    rng: random.Random,
    progress: Progress | None = None,
) -> TodayProblems:
    """Make today's problems with their own connections to the cache and the history.

    This runs in a background thread while the start screen is shown. SQLite
    connections cannot be shared between threads, so the cache and the history
    are opened here and closed at the end.

    Args:
        settings_path: Path of the settings file (the cache and the history are next to it).
        folder_argument: The games folder given on the command line, or None.
        settings: All settings (the quiz and the review settings are used).
        rng: The random number generator, for the random order.
        progress: Called with (files done, all files) while the SGF files are read.

    Returns:
        Today's problems, or why there are none.
    """
    history = open_history(settings_path)  # If it cannot be opened, main() has already told the user.
    notices: list[Notice] = []
    cache = open_cache(settings_path, notices)
    try:
        colors = read_recorded_colors(settings_path)
        today = prepare_problems(folder_argument, settings, history, rng, cache, progress, colors)
        return replace(today, notices=notices + today.notices)
    finally:
        if cache is not None:
            cache.close()
        if history is not None:
            history.store.close()


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
        problems, _ = collect_problems(
            folder, settings.extract, cache, recorded_colors=read_recorded_colors(settings_path)
        )
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
