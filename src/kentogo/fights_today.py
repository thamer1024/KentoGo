"""Today's local fight problems (life and death, broken boundaries; see mistakes.local_fight).

The fights are made from the games of the quiz's games folder, with the problem cache, as the mistake problems
are (see today). They have their own history (FIGHT_HISTORY_FILE_NAME, next to the settings file) and their own
review settings (AppSettings.fights), so that their reviews and their limit of the day are counted apart from
the mistake problems. They are reviewed in the same way (see repetition): a fight answered wrong comes back
the next day, and the correct answers in a row make the wait longer.

Only the fights made from the games are asked: when a game is analyzed again and a fight is no longer found,
its reviews are not asked any more.
"""

from __future__ import annotations

import random
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from kentogo.app_settings import AppSettings
from kentogo.mistakes.local_fight import LocalFight
from kentogo.notice import Notice
from kentogo.quiz.collect import collect_games
from kentogo.quiz.order import keep_newest, order_problems
from kentogo.quiz.problem_cache import ProblemCache
from kentogo.repetition.daily import answered_on, left_today
from kentogo.repetition.modes import REVIEW_ONCE
from kentogo.repetition.plan import QuizPlan, plan_problems
from kentogo.repetition.schedule import review_state
from kentogo.review.history import AnswerHistory
from kentogo.review.review_settings import ReviewSettings
from kentogo.today import Progress, find_games_folder, open_answers, open_cache, read_recorded_colors

FIGHT_HISTORY_FILE_NAME = "fight_history.sqlite3"


@dataclass(frozen=True)
class TodayFights:
    """Today's local fight problems.

    Attributes:
        fights: The fights to ask, in order.
        message: Why there are no fights (None when there are fights).
        new_count: How many of them were never answered.
        review_count: How many of them are reviews.
        session_limit: How many more fights may be asked today, reviews included (None: no limit).
        notices: Problems to tell the user in a dialog (for example that the cache cannot be used).
    """

    fights: list[LocalFight]
    message: Notice | None = None
    new_count: int = 0
    review_count: int = 0
    session_limit: int | None = None
    notices: list[Notice] = field(default_factory=list)


def fight_history_path(settings_path: Path) -> Path:
    """Return the path of the history of the local fights (next to the settings file)."""
    return settings_path.expanduser().parent / FIGHT_HISTORY_FILE_NAME


def plan_fights(
    fights: list[LocalFight], history: AnswerHistory, settings: ReviewSettings, today: date
) -> tuple[QuizPlan[LocalFight], int | None]:
    """Choose today's fights: new fights and the reviews that are due, in the order of the settings.

    Answers before the last reset are not used, and fights set aside are not asked.

    Returns:
        A tuple (plan, limit). limit is how many more fights may be asked today, reviews included
        (see repetition.daily), or None if there is no limit.
    """
    answers = history.all_previous()
    done = answered_on((record.answered_at for records in answers.values() for record in records), today)
    last_before_reset = history.last_reset()
    once = settings.review_mode == REVIEW_ONCE
    states = {}
    for fight in fights:
        records = [record for record in answers.get(fight.problem_id, []) if record.record_id > last_before_reset]
        states[fight.problem_id] = review_state(records, settings.review_streak, once)
    limit = left_today(settings.daily_limit, done)
    plan = plan_problems(fights, states, today, settings.priority, history.exclusions(), limit)
    return plan, limit


def prepare_fights(
    folder_argument: Path | None,
    settings: AppSettings,
    history: AnswerHistory | None,
    rng: random.Random,
    cache: ProblemCache | None = None,
    progress: Progress | None = None,
    recorded_colors: Mapping[str, str] | None = None,
) -> TodayFights:
    """Make the fights to ask today, and print what was found.

    Without a history, all fights are asked (it is not known which were answered).

    Args:
        folder_argument: The games folder given on the command line, or None.
        settings: All settings (the quiz's games and order, and the fights' review settings are used).
        history: The history of the fights, or None if it cannot be used.
        rng: The random number generator, for the random order.
        cache: The problem cache, or None to read every file.
        progress: Called with (files done, all files) while the SGF files are read.
        recorded_colors: The user's color that the user gave, by the name of the SGF file.
    """
    folder, folder_problem = find_games_folder(folder_argument, settings.quiz.games_folder)
    if folder is None:
        return TodayFights([], folder_problem)
    games, _skipped = collect_games(folder, settings.quiz.extract, cache, progress, recorded_colors)
    fights = [fight for _path, result in games for fight in result.local_fights]
    fights = order_problems(keep_newest(fights), settings.quiz.order, rng)
    if history is None:
        print(f"{len(fights)} local fights (no history)", file=sys.stderr)
        return TodayFights(fights, None, len(fights))
    plan, limit = plan_fights(fights, history, settings.fights, date.today())
    print(f"{len(fights)} local fights: {plan.new_count} new, {plan.review_count} reviews today", file=sys.stderr)
    notices = [Notice("notice_history_error", {"reason": history.last_error})] if history.last_error else []
    if not plan.problems:
        message = Notice("fights_none" if not fights else "daily_done" if limit == 0 else "nothing_today")
        return TodayFights([], message, session_limit=limit, notices=notices)
    return TodayFights(plan.problems, None, plan.new_count, plan.review_count, limit, notices)


def load_fights(
    settings_path: Path,
    folder_argument: Path | None,
    settings: AppSettings,
    rng: random.Random,
    progress: Progress | None = None,
) -> TodayFights:
    """Make today's fights with their own connections to the cache and the history (for a background thread).

    Args:
        settings_path: Path of the settings file (the cache and the histories are next to it).
        folder_argument: The games folder given on the command line, or None.
        settings: All settings.
        rng: The random number generator, for the random order.
        progress: Called with (files done, all files) while the SGF files are read.
    """
    notices: list[Notice] = []
    history = open_answers(fight_history_path(settings_path), notices)
    cache = open_cache(settings_path, notices)
    try:
        colors = read_recorded_colors(settings_path)
        today = prepare_fights(folder_argument, settings, history, rng, cache, progress, colors)
        return replace(today, notices=notices + today.notices)
    finally:
        if cache is not None:
            cache.close()
        if history is not None:
            history.store.close()
