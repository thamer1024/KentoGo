"""Choose the games to count in the territory counting practice, as the settings say.

The games are the SGF files of the games folder. They are put in the order of the
settings (file name, newest, random); then games never counted and games to count
again (counted badly before, and their day has come, see repetition.schedule) are
ordered as in the quiz (see repetition.plan): new ones first, the ones to count again
first, or a mix. Games counted well, and games whose day has not come, are not asked.

Only games that ended by counting can be used (see final_position). Whether a game did
is known only when its file is read, so the files are read one by one, in the order of
the plan, until such a game is found. When the limit of the settings is reached (the
games counted in this start of the app), no more games are given.
"""

from __future__ import annotations

import os
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from kentogo.repetition.daily import answered_on
from kentogo.repetition.plan import plan_problems
from kentogo.repetition.schedule import STATE_REVIEW, review_state
from kentogo.seichi.final_position import FinishedGame, read_finished_game
from kentogo.seichi.seichi_history import SeichiHistory, SeichiRecord
from kentogo.seichi.seichi_settings import ORDER_FILE_NAME, ORDER_NEWEST, SeichiSettings


@dataclass(frozen=True)
class GameFile:
    """An SGF file of the games folder, as a game to count.

    Attributes:
        path: The file.
        problem_id: The name of the file: how the game is known in the history.
        review: True if the game is counted again (it was counted badly before).
    """

    path: Path
    problem_id: str
    review: bool = False


@dataclass(frozen=True)
class SeichiGame:
    """A game to count.

    Attributes:
        game: The game, with its final position.
        problem_id: How the game is known in the history.
        review: True if it is counted again.
    """

    game: FinishedGame
    problem_id: str
    review: bool


class SeichiQueue:
    """The games to count in this start of the app, in order.

    Attributes:
        limit: The most games to count in a day (None: no limit).
        done_before: How many games were counted today before this start.
        counted: How many games have been counted (judged by the user) in this start.
    """

    def __init__(self, files: list[GameFile], limit: int | None, done_before: int = 0):
        """Keep the planned files (see plan_games)."""
        self._files: Iterator[GameFile] = iter(files)
        self.limit = limit
        self.done_before = done_before
        self.counted = 0

    @property
    def today_count(self) -> int:
        """How many games have been counted today (before and in this start)."""
        return self.done_before + self.counted

    @property
    def finished(self) -> bool:
        """True when the limit of the day has been reached (it is cleared at midnight)."""
        return self.limit is not None and self.today_count >= self.limit

    def next_game(self) -> SeichiGame | None:
        """Return the next game that ended by counting, or None when there is none (or the limit is reached).

        Files that cannot be read, and games that did not end by counting, are skipped.
        """
        if self.finished:
            return None
        for file in self._files:
            try:
                game = read_finished_game(file.path)
            except Exception:  # A broken file is skipped.
                continue
            if game is not None:
                return SeichiGame(game, file.problem_id, file.review)
        return None

    def count_one(self) -> None:
        """Count one more game as done in this start."""
        self.counted += 1


def plan_games(
    folder: Path,
    settings: SeichiSettings,
    results: dict[str, list[SeichiRecord]],
    today: date,
    chooser: random.Random | None = None,
    modified_time: Callable[[Path], float] = os.path.getmtime,
) -> list[GameFile]:
    """Return the files of the games to count today, in the order of the settings (see the module).

    Args:
        folder: The games folder (its subfolders are not read).
        settings: The settings of the practice.
        results: The results so far, from each game (file name) to its results, the oldest first.
        today: Today's date.
        chooser: The random numbers for the random order (a new one when not given).
        modified_time: Returns when a file was last changed. Tests pass a fake one.
    """
    files = sorted(folder.glob("*.sgf"))
    if settings.order == ORDER_NEWEST:
        files.sort(key=modified_time, reverse=True)
    elif settings.order != ORDER_FILE_NAME:
        (chooser or random.Random()).shuffle(files)
    states = {name: review_state(records, settings.review_streak, settings.once) for name, records in results.items()}
    plan = plan_problems([GameFile(path, path.name) for path in files], states, today, settings.priority)
    reviews = {name for name, state in states.items() if state.state == STATE_REVIEW}
    return [GameFile(file.path, file.problem_id, file.problem_id in reviews) for file in plan.problems]


def start_queue(
    folder: Path,
    settings: SeichiSettings,
    results: dict[str, list[SeichiRecord]],
    today: date,
    chooser: random.Random | None = None,
) -> SeichiQueue:
    """Plan the games of this start of the app (see plan_games), with the daily limit of the settings.

    The games counted today before this start count toward the limit (see repetition.daily).
    """
    files = plan_games(folder, settings, results, today, chooser)
    done = answered_on((record.answered_at for records in results.values() for record in records), today)
    return SeichiQueue(files, settings.daily_limit or None, done)


def queue_from_history(
    folder: Path, settings: SeichiSettings, history: SeichiHistory | None, today: date
) -> SeichiQueue:
    """Plan the games of this start of the app from the results in the history (none without a history)."""
    results = history.all_results() if history is not None else {}
    return start_queue(folder, settings, results, today)
