"""Ask the problems of the games analyzed by KentoGo, to try them out (python -m kentogo.app --test-quiz KIND).

The trial asks every problem of one kind at once, from the games of the games folder that KentoGo
analyzed (their root has KGM[KentoGo]; see analysis_run.analyzed_by_kentogo):

- TRIAL_LOSS: the user's own mistakes that are not punishment problems (the problems by the points lost).
- TRIAL_PUNISH: the punishment problems (the opponent's big mistakes that the user did not punish),
  also those beyond the problems of a game (see mistakes.extract.ExtractResult.punishments).

The history is not used: the daily limit, the reviews and the problems set aside do not count, and
the answers are not saved (the app is started without a history; see app.main).

When there are no problems, the message tells the folder, how many games were read and how many of
them KentoGo analyzed, so that the user can see why.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from kentogo.analysis_run import analyzed_by_kentogo
from kentogo.app_settings import AppSettings
from kentogo.common.sgf import load_game
from kentogo.mistakes.extract import PUNISH, ExtractResult
from kentogo.mistakes.problem import Problem
from kentogo.notice import Notice
from kentogo.quiz.collect import collect_games
from kentogo.quiz.order import keep_newest
from kentogo.today import Progress, TodayProblems, find_games_folder, open_cache, read_recorded_colors

TRIAL_LOSS = "loss"  # The user's own mistakes, without the punishment problems.
TRIAL_PUNISH = "punish"  # Only the punishment problems.
TRIAL_KINDS = (TRIAL_LOSS, TRIAL_PUNISH)


def kentogo_games(
    games: Iterable[tuple[Path, ExtractResult]], by_kentogo: Callable[[Path], bool]
) -> list[tuple[Path, ExtractResult]]:
    """Return the games that KentoGo analyzed.

    Args:
        games: Each game file and the problems made from it (see quiz.collect.collect_games).
        by_kentogo: True for a game file that KentoGo analyzed (see analyzed_by_kentogo_file).
    """
    return [(path, result) for path, result in games if by_kentogo(path)]


def trial_problems(games: Iterable[tuple[Path, ExtractResult]], kind: str) -> list[Problem]:
    """Return the problems of one kind of some games (see kentogo_games), game by game.

    Args:
        games: Each game file and the problems made from it.
        kind: One of TRIAL_KINDS.
    """
    problems: list[Problem] = []
    for _path, result in games:
        problems += problems_of_trial(result, kind)
    return keep_newest(problems)


def problems_of_trial(result: ExtractResult, kind: str) -> list[Problem]:
    """Return the problems of one kind of a game (see TRIAL_KINDS)."""
    if kind == TRIAL_PUNISH:
        return [problem for problem in result.problems if problem.punishment == PUNISH] + list(result.punishments)
    return [problem for problem in result.problems if problem.punishment != PUNISH]


def analyzed_by_kentogo_file(path: Path) -> bool:
    """True if KentoGo analyzed the game of a file (a file that cannot be read gives False)."""
    try:
        return analyzed_by_kentogo(load_game(path))
    except Exception:  # A broken file has no problems anyway.
        return False


def load_trial(
    settings_path: Path,
    folder_argument: Path | None,
    settings: AppSettings,
    kind: str,
    progress: Progress | None = None,
) -> TodayProblems:
    """Make the problems of the trial, in the background thread of the start screen (see load_today).

    Args:
        settings_path: Path of the settings file (the problem cache is next to it).
        folder_argument: The games folder given on the command line, or None.
        settings: All settings (the conditions of the problems are used).
        kind: One of TRIAL_KINDS.
        progress: Called with (files done, all files) while the SGF files are read.

    Returns:
        All the problems of the kind, with a notice that this is a trial (or why there are none).
    """
    folder, folder_problem = find_games_folder(folder_argument, settings.quiz.games_folder)
    if folder is None:
        return TodayProblems([], folder_problem)
    notices: list[Notice] = []
    cache = open_cache(settings_path, notices)
    try:
        colors = read_recorded_colors(settings_path)
        games, skipped = collect_games(folder, settings.quiz.extract, cache, progress, colors)
    finally:
        if cache is not None:
            cache.close()
    ours = kentogo_games(games, analyzed_by_kentogo_file)
    problems = trial_problems(ours, kind)
    files = len(games) + len(skipped)
    print(f"trial ({kind}): {len(problems)} problems of {len(ours)} games analyzed by KentoGo", file=sys.stderr)
    print(f"trial ({kind}): {files} games in {folder}", file=sys.stderr)
    if not problems:
        message = Notice("trial_no_problems", {"folder": folder, "files": files, "games": len(ours)})
        return TodayProblems([], message, notices=notices, skipped_games=skipped)
    notices.append(Notice(f"notice_trial_{kind}", {"count": len(problems)}))
    return TodayProblems(problems, None, len(problems), 0, notices=notices, skipped_games=skipped)


def trial_loader(
    settings_path: Path, folder_argument: Path | None, settings: AppSettings, kind: str
) -> Callable[[Progress], TodayProblems]:
    """Return the function that the start screen calls to make the problems of the trial."""
    return lambda progress: load_trial(settings_path, folder_argument, settings, kind, progress)
