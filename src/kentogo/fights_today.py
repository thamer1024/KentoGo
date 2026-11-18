"""Today's local fight problems (life and death, broken boundaries; see mistakes.local_fight).

The fights are made from the games of the quiz's games folder, with the problem cache, as the mistake problems
are (see today). They have their own history (FIGHT_HISTORY_FILE_NAME, next to the settings file) and their own
review settings (AppSettings.fights), so that their reviews and their limit of the day are counted apart from
the mistake problems. They are reviewed in the same way (see repetition): a fight answered wrong comes back
the next day, and the correct answers in a row make the wait longer.

Only the fights made from the games are asked: when a game is analyzed again and a fight is no longer found,
its reviews are not asked any more. A fight with no point to judge is not asked either (see askable_fights).
"""

from __future__ import annotations

import random
import sys
from collections.abc import Mapping, Set
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from kentogo.app_settings import AppSettings
from kentogo.commentary_inputs import read_recorded_colors
from kentogo.games_folder import find_games_folder
from kentogo.mistakes.local_fight import LocalFight
from kentogo.notice import Notice
from kentogo.practice_stores import open_answers, open_cache
from kentogo.quiz.collect import Progress, collect_games
from kentogo.quiz.fight_judge import judged_points
from kentogo.quiz.order import keep_newest, order_problems
from kentogo.quiz.problem_cache import ProblemCache
from kentogo.repetition.counts import ProblemCounts, count_problems
from kentogo.repetition.daily import answered_on, left_today
from kentogo.repetition.modes import REVIEW_ONCE
from kentogo.repetition.plan import QuizPlan, plan_problems
from kentogo.repetition.schedule import answer_day, review_state
from kentogo.review.answer_states import answers_and_states
from kentogo.review.history import AnswerHistory
from kentogo.review.review_settings import ReviewSettings

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
        all_ids: The IDs of all the fights made from the games, also those not asked today. The summary of the
            day counts them, so that it need not read the games again.
    """

    fights: list[LocalFight]
    message: Notice | None = None
    new_count: int = 0
    review_count: int = 0
    session_limit: int | None = None
    notices: list[Notice] = field(default_factory=list)
    all_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FightSummary:
    """The summary of the day for the local fights.

    Attributes:
        answered: How many fights were judged today.
        correct: How many of them were won.
        counts: How far the current fights are.
    """

    answered: int
    correct: int
    counts: ProblemCounts = ProblemCounts()


def fight_summary(
    history: AnswerHistory, today: date, fight_ids: Set[str], settings: ReviewSettings
) -> FightSummary | None:
    """Return the summary of the fights answered today, or None if there are none.

    Args:
        history: The history of the fights.
        today: Today's date.
        fight_ids: The IDs of all the fights made from the games. Fights set aside are not counted.
        settings: The review settings of the fights.
    """
    answers, states = answers_and_states(history, settings)
    todays = [answer for answer in answers if answer.correct is not None and answer_day(answer) == today]
    if not todays:
        return None
    counts = count_problems(set(fight_ids) - history.exclusions(), states)
    return FightSummary(len(todays), sum(1 for answer in todays if answer.correct), counts)


def load_fight_summary(
    settings_path: Path, today: date, fight_ids: Set[str], settings: ReviewSettings
) -> FightSummary | None:
    """Read the history of the fights and make the summary of the day (for a background thread)."""
    history = open_answers(fight_history_path(settings_path))
    if history is None:
        return None
    try:
        return fight_summary(history, today, fight_ids, settings)
    finally:
        history.store.close()


def fight_history_path(settings_path: Path) -> Path:
    """Return the path of the history of the local fights (next to the settings file)."""
    return settings_path.expanduser().parent / FIGHT_HISTORY_FILE_NAME


def askable_fights(fights: list[LocalFight]) -> list[LocalFight]:
    """Return the fights that have points to judge (the stones, or the empty points of a boundary)."""
    return [fight for fight in fights if judged_points(fight)]


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
    fights = order_problems(keep_newest(askable_fights(fights)), settings.quiz.order, rng)
    all_ids = frozenset(fight.problem_id for fight in fights)
    if history is None:
        print(f"{len(fights)} local fights (no history)", file=sys.stderr)
        return TodayFights(fights, None, len(fights), all_ids=all_ids)
    plan, limit = plan_fights(fights, history, settings.fights, date.today())
    print(f"{len(fights)} local fights: {plan.new_count} new, {plan.review_count} reviews today", file=sys.stderr)
    notices = [Notice("notice_history_error", {"reason": history.last_error})] if history.last_error else []
    if not plan.problems:
        message = Notice("fights_none" if not fights else "daily_done" if limit == 0 else "nothing_today")
        return TodayFights([], message, session_limit=limit, notices=notices, all_ids=all_ids)
    return TodayFights(plan.problems, None, plan.new_count, plan.review_count, limit, notices, all_ids)


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
