"""The report (成績表): numbers that show how the practice goes, made from the history and the games.

The practice is counted by practice days (days with at least one answer), never by weeks, so
that days without practice do not pull the numbers down: "recent" means the latest RECENT
practice days, compared with the RECENT before them. The mistakes in the games are counted per
game, the latest games last. Days in a row are not counted on purpose: one day off would reset
them to 0.

The same numbers make the summary of the day (today_summary), shown when the user leaves the
quiz, with what was achieved today: a stage cleared (see quiz.stages), and each 100 correct
answers and each 1,000 points got back in all.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from kentogo.app_settings import AppSettings
from kentogo.mistakes.problem import Problem
from kentogo.quiz.collect import collect_problems
from kentogo.quiz.order import keep_newest
from kentogo.quiz.problem_cache import ProblemCache
from kentogo.quiz.score import score_answer
from kentogo.quiz.stages import StageStatus, current_stage
from kentogo.repetition.modes import REVIEW_ONCE
from kentogo.repetition.schedule import STATE_DONE, ReviewState, review_state
from kentogo.review.history import AnswerHistory
from kentogo.today import find_games_folder, open_cache, open_history, read_recorded_colors

RECENT = 5  # How many practice days (or games) are "recent".
BIG_LOSS = 20.0  # A mistake of at least this many points is big.
LARGE_LOSS = 10.0  # A mistake of at least this many points (and less than BIG_LOSS) is large.
CORRECT_STEP = 100  # A milestone at each this many correct answers in all.
RECOVERED_STEP = 1000  # A milestone at each this many points got back in all.

# The date and time in the file names of KaTrain, such as "2026-10-30 17 43 32".
_FILE_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _T](\d{2})[ _:.-]?(\d{2})[ _:.-]?(\d{2})")


class Answer(Protocol):
    """An answer of the history, such as review.record.AnswerRecord. Nothing else is needed."""

    problem_id: str
    answered_at: str
    actual_loss: float | None
    answer_loss: float | None
    correct: bool | None


@dataclass(frozen=True)
class DayResult:
    """The answers of one practice day.

    Attributes:
        day: The day.
        answered: How many answers were judged.
        correct: How many of them were correct.
        average: The average part of the loss got back in the answers to normal problems
            (0.0 to 1.0), or None if there were none.
        recovered: The points got back by the correct answers.
    """

    day: date
    answered: int
    correct: int
    average: float | None
    recovered: float


@dataclass(frozen=True)
class GameMistakes:
    """The big mistakes of one game.

    Attributes:
        name: The file name of the game.
        played: When it was played (from the file name, or the time the file was changed).
        big: How many mistakes lost at least BIG_LOSS points.
        large: How many lost at least LARGE_LOSS points, and less than BIG_LOSS.
    """

    name: str
    played: datetime
    big: int
    large: int


@dataclass(frozen=True)
class Recent:
    """The latest RECENT practice days, and the RECENT before them (None when there are none).

    Attributes:
        correct_rate: The part of the answers that were correct (0.0 to 1.0).
        average: The average part of the loss got back in the answers to normal problems.
        earlier_correct_rate: The same for the practice days before them.
        earlier_average: The same for the practice days before them.
    """

    correct_rate: float | None = None
    average: float | None = None
    earlier_correct_rate: float | None = None
    earlier_average: float | None = None


@dataclass(frozen=True)
class GameAverages:
    """The average number of big mistakes per game: the latest RECENT games, and the RECENT before them.

    Attributes:
        big: Mistakes of at least BIG_LOSS points per game in the latest games (None without games).
        large: Mistakes of LARGE_LOSS to BIG_LOSS points per game in the latest games.
        earlier_big: The same for the games before them.
        earlier_large: The same for the games before them.
    """

    big: float | None = None
    large: float | None = None
    earlier_big: float | None = None
    earlier_large: float | None = None


@dataclass(frozen=True)
class Totals:
    """The numbers of all the practice.

    Attributes:
        answered: How many answers were judged.
        correct: How many of them were correct.
        finished: How many problems are finished (see repetition.schedule).
        recovered: The points got back by the correct answers.
        days: On how many days the user practiced.
    """

    answered: int = 0
    correct: int = 0
    finished: int = 0
    recovered: float = 0.0
    days: int = 0


@dataclass(frozen=True)
class Report:
    """Everything the report screen shows.

    Attributes:
        totals: The numbers of all the practice.
        recent: The latest practice days compared with the ones before.
        days: Each practice day, the oldest first.
        games: The big mistakes of each game, the oldest first.
        game_averages: The latest games compared with the ones before.
        pass_ratio: The pass ratio used now (a line on the chart of the days).
    """

    totals: Totals = Totals()
    recent: Recent = Recent()
    days: list[DayResult] = field(default_factory=list)
    games: list[GameMistakes] = field(default_factory=list)
    game_averages: GameAverages = GameAverages()
    pass_ratio: float = 0.0


@dataclass(frozen=True)
class Achievement:
    """Something achieved today.

    Attributes:
        key: The kind: "stage_cleared", "correct_milestone" or "recovered_milestone".
        value: The threshold of the stage, the number of correct answers, or the points.
    """

    key: str
    value: float


@dataclass(frozen=True)
class TodaySummary:
    """The summary of the day.

    Attributes:
        answered: How many answers were judged today.
        correct: How many of them were correct.
        recovered: The points got back today.
        day_number: The number of this practice day (1 for the first day).
        achievements: What was achieved today.
    """

    answered: int
    correct: int
    recovered: float
    day_number: int
    achievements: tuple[Achievement, ...] = ()


def answer_day(answer: Answer) -> date:
    """Return the day of an answer, in the computer's time zone."""
    return datetime.fromisoformat(answer.answered_at).astimezone().date()


def recovered_points(answer: Answer) -> float:
    """Return the points that a correct answer got back compared with the game move (0 otherwise)."""
    if not answer.correct or answer.actual_loss is None or answer.answer_loss is None:
        return 0.0
    return max(0.0, answer.actual_loss - max(answer.answer_loss, 0.0))


def day_results(answers: Iterable[Answer], small_problem_threshold: float) -> list[DayResult]:
    """Return the results of each practice day, the oldest first (answers that were not judged are left out)."""
    by_day: dict[date, list[Answer]] = defaultdict(list)
    for answer in answers:
        if answer.correct is not None:
            by_day[answer_day(answer)].append(answer)
    return [_day_result(day, by_day[day], small_problem_threshold) for day in sorted(by_day)]


def _day_result(day: date, answers: list[Answer], small_problem_threshold: float) -> DayResult:
    """Return the result of the answers of one day."""
    scores = _scores(answers, small_problem_threshold)
    return DayResult(
        day,
        len(answers),
        sum(1 for answer in answers if answer.correct),
        sum(scores) / len(scores) if scores else None,
        sum(recovered_points(answer) for answer in answers),
    )


def _scores(answers: Iterable[Answer], small_problem_threshold: float) -> list[float]:
    """Return the part of the loss got back by each answer to a normal problem with both losses known."""
    return [
        score_answer(answer.actual_loss, answer.answer_loss)
        for answer in answers
        if answer.actual_loss is not None
        and answer.answer_loss is not None
        and answer.actual_loss >= small_problem_threshold
    ]


def recent_results(answers: Iterable[Answer], small_problem_threshold: float) -> Recent:
    """Compare the latest RECENT practice days with the RECENT before them (all their answers together)."""
    by_day: dict[date, list[Answer]] = defaultdict(list)
    for answer in answers:
        if answer.correct is not None:
            by_day[answer_day(answer)].append(answer)
    days = sorted(by_day)
    latest = [answer for day in days[-RECENT:] for answer in by_day[day]]
    earlier = [answer for day in days[-2 * RECENT : -RECENT] for answer in by_day[day]]
    return Recent(
        _correct_rate(latest),
        _average(latest, small_problem_threshold),
        _correct_rate(earlier),
        _average(earlier, small_problem_threshold),
    )


def _correct_rate(answers: list[Answer]) -> float | None:
    """Return the part of the answers that were correct, or None without answers."""
    return sum(1 for answer in answers if answer.correct) / len(answers) if answers else None


def _average(answers: list[Answer], small_problem_threshold: float) -> float | None:
    """Return the average part of the loss got back, or None without answers to normal problems."""
    scores = _scores(answers, small_problem_threshold)
    return sum(scores) / len(scores) if scores else None


def totals(answers: Sequence[Answer], states: Mapping[str, ReviewState]) -> Totals:
    """Return the numbers of all the practice (answers that were not judged are left out)."""
    judged = [answer for answer in answers if answer.correct is not None]
    return Totals(
        len(judged),
        sum(1 for answer in judged if answer.correct),
        sum(1 for state in states.values() if state.state == STATE_DONE),
        sum(recovered_points(answer) for answer in judged),
        len({answer_day(answer) for answer in judged}),
    )


def game_time(path: Path, modified_time: Callable[[Path], float] = os.path.getmtime) -> datetime:
    """Return when a game was played: from the date and time in its file name, or the time the file was changed."""
    match = _FILE_TIME.search(path.name)
    if match:
        try:
            return datetime(*(int(part) for part in match.groups()))
        except ValueError:
            pass
    return datetime.fromtimestamp(modified_time(path))


def game_mistakes(problems: Iterable[Problem], games: Mapping[Path, datetime]) -> list[GameMistakes]:
    """Return the big mistakes of each game, the oldest first (games without big mistakes count too).

    Args:
        problems: The problems made from the games.
        games: The games that problems are made from, with the time each was played.
    """
    big: dict[str, int] = defaultdict(int)
    large: dict[str, int] = defaultdict(int)
    for problem in problems:
        name = Path(problem.sgf_path).name
        if problem.points_lost >= BIG_LOSS:
            big[name] += 1
        elif problem.points_lost >= LARGE_LOSS:
            large[name] += 1
    rows = [GameMistakes(path.name, played, big[path.name], large[path.name]) for path, played in games.items()]
    return sorted(rows, key=lambda row: (row.played, row.name))


def game_averages(games: Sequence[GameMistakes]) -> GameAverages:
    """Return the average big mistakes per game of the latest RECENT games and of the RECENT before them."""
    latest, earlier = games[-RECENT:], games[-2 * RECENT : -RECENT]
    return GameAverages(
        _per_game(latest, "big"), _per_game(latest, "large"), _per_game(earlier, "big"), _per_game(earlier, "large")
    )


def _per_game(games: Sequence[GameMistakes], kind: str) -> float | None:
    """Return the average of one kind of mistakes ("big" or "large") per game, or None without games."""
    return sum(getattr(game, kind) for game in games) / len(games) if games else None


def today_summary(
    answers: Sequence[Answer], today: date, problems: Collection[Problem], stages: tuple[float, ...]
) -> TodaySummary | None:
    """Return the summary of today, or None if nothing was answered today.

    Args:
        answers: All answers of the history, the oldest first.
        today: Today's date.
        problems: All problems (for the stages).
        stages: The thresholds of the staged problems, or () if they are not used.
    """
    judged = [answer for answer in answers if answer.correct is not None]
    before = [answer for answer in judged if answer_day(answer) < today]
    todays = [answer for answer in judged if answer_day(answer) == today]
    if not todays:
        return None
    recovered_before = sum(recovered_points(answer) for answer in before)
    recovered_today = sum(recovered_points(answer) for answer in todays)
    correct_before = sum(1 for answer in before if answer.correct)
    correct_today = sum(1 for answer in todays if answer.correct)
    achievements = _stages_cleared(before, judged, problems, stages)
    achievements += _milestones("correct_milestone", correct_before, correct_before + correct_today, CORRECT_STEP)
    achievements += _milestones(
        "recovered_milestone", recovered_before, recovered_before + recovered_today, RECOVERED_STEP
    )
    day_number = len({answer_day(answer) for answer in judged})
    return TodaySummary(len(todays), correct_today, recovered_today, day_number, tuple(achievements))


def _stages_cleared(
    before: Sequence[Answer], judged: Sequence[Answer], problems: Collection[Problem], stages: tuple[float, ...]
) -> list[Achievement]:
    """Return the stages cleared today: those of the stage before today up to the stage now."""
    if not stages:
        return []
    then = _cleared_count(current_stage(problems, {a.problem_id for a in before if a.correct}, stages))
    now = _cleared_count(current_stage(problems, {a.problem_id for a in judged if a.correct}, stages))
    return [Achievement("stage_cleared", stages[index]) for index in range(then, now)]


def _cleared_count(status: StageStatus) -> int:
    """Return how many stages are cleared (all of them when nothing is left in the last one)."""
    return status.index if status.left > 0 else status.index + 1


def _milestones(key: str, before: float, now: float, step: int) -> list[Achievement]:
    """Return the milestones (each step) passed between two totals."""
    return [Achievement(key, value) for value in range((int(before) // step + 1) * step, int(now) + 1, step)]


@dataclass(frozen=True)
class _Material:
    """What the report is made from: the problems, the games, the answers and the state of each problem."""

    problems: list[Problem]
    games: dict[Path, datetime]
    answers: list[Answer]
    states: dict[str, ReviewState]


def build_report(material: _Material, settings: AppSettings) -> Report:
    """Make the report from what was read."""
    threshold = settings.quiz.scoring.small_problem_threshold
    games = game_mistakes(material.problems, material.games)
    return Report(
        totals(material.answers, material.states),
        recent_results(material.answers, threshold),
        day_results(material.answers, threshold),
        games,
        game_averages(games),
        settings.quiz.scoring.pass_ratio,
    )


def load_report(settings_path: Path, folder_argument: Path | None, settings: AppSettings) -> Report:
    """Read the games and the history, and make the report (called in a background thread)."""
    return build_report(_read(settings_path, folder_argument, settings), settings)


def load_today_summary(
    settings_path: Path, folder_argument: Path | None, settings: AppSettings, today: date
) -> TodaySummary | None:
    """Read the games and the history, and make the summary of the day (None if nothing was answered today)."""
    material = _read(settings_path, folder_argument, settings)
    return today_summary(material.answers, today, material.problems, settings.quiz.extract.loss_stages)


def _read(settings_path: Path, folder_argument: Path | None, settings: AppSettings) -> _Material:
    """Read the problems and the games of the games folder (using the cache), and the history."""
    history = open_history(settings_path)
    cache = open_cache(settings_path)
    try:
        problems, games = _games(settings_path, folder_argument, settings, cache)
        answers, states = _answers(history, settings)
        return _Material(problems, games, answers, states)
    finally:
        if cache is not None:
            cache.close()
        if history is not None:
            history.store.close()


def _games(
    settings_path: Path, folder_argument: Path | None, settings: AppSettings, cache: ProblemCache | None
) -> tuple[list[Problem], dict[Path, datetime]]:
    """Return the problems and the games (with the time each was played) of the games folder."""
    folder, _problem = find_games_folder(folder_argument, settings.quiz.games_folder)
    if folder is None:
        return [], {}
    colors = read_recorded_colors(settings_path)
    problems, skipped = collect_problems(folder, settings.quiz.extract, cache, None, colors)
    left_out = {game.name for game in skipped}
    games = {path: game_time(path) for path in sorted(folder.glob("*.sgf")) if path.name not in left_out}
    return keep_newest(problems), games


def _answers(history: AnswerHistory | None, settings: AppSettings) -> tuple[list[Answer], dict[str, ReviewState]]:
    """Return all answers, the oldest first, and the state of each answered problem (since the last reset)."""
    if history is None:
        return [], {}
    by_problem = history.all_previous()
    last_reset = history.last_reset()
    once = settings.review.review_mode == REVIEW_ONCE
    states = {
        problem_id: review_state(
            [record for record in records if record.record_id > last_reset], settings.review.review_streak, once
        )
        for problem_id, records in by_problem.items()
    }
    answers = sorted((record for records in by_problem.values() for record in records), key=lambda r: r.record_id)
    return answers, states
