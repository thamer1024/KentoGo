"""Make problems from all SGF files in a folder, using the problem cache when it can.

Files that have not changed since the last start are not read again: their
problems come from the cache (see problem_cache). New and changed files are
read, and what was made from them is kept in the cache for the next start.
A broken file is reported, and does not stop the other files.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from kentogo.common.sgf import load_game
from kentogo.mistakes.extract import ExtractResult, ExtractSettings, extract_problems
from kentogo.mistakes.problem import Problem
from kentogo.quiz.problem_cache import CachedFile, FileStamp, ProblemCache, settings_key

REASON_CANNOT_READ = "cannot_read"  # The file is broken or cannot be opened.


@dataclass(frozen=True)
class SkippedGame:
    """A game that gave no problems, and why.

    Attributes:
        name: The file name.
        reason: REASON_CANNOT_READ, or a reason of extract (such as REASON_UNKNOWN_COLOR).
        detail: The error, when the file could not be read.
    """

    name: str
    reason: str
    detail: str = ""

    def message(self) -> str:
        """Return a line for the console."""
        if self.reason == REASON_CANNOT_READ:
            return f"{self.name}: cannot read ({self.detail})"
        return f"{self.name}: skipped ({self.reason})"


def collect_problems(
    folder: Path,
    settings: ExtractSettings,
    cache: ProblemCache | None = None,
    progress: Callable[[int, int], None] | None = None,
    recorded_colors: Mapping[str, str] | None = None,
) -> tuple[list[Problem], list[SkippedGame]]:
    """Make problems from all SGF files in a folder (not in its subfolders).

    Args:
        folder: The folder.
        settings: Conditions for choosing problems.
        cache: The problem cache, or None to read every file.
        progress: Called with (files done, all files) after each file, to show the progress.
        recorded_colors: The user's color that the user gave, by the name of the SGF file
            (see commentary.history). It is used before any other way to find the color.

    Returns:
        A tuple (problems, skipped). The problems are in the order of the file names,
        and from the largest loss to the smallest in each file. skipped tells which
        files could not be read, had no user color, or had no analysis.
    """
    problems: list[Problem] = []
    skipped: list[SkippedGame] = []
    paths = sorted(folder.glob("*.sgf"))
    key = settings_key(settings)
    colors = recorded_colors or {}
    for done, path in enumerate(paths, start=1):
        game = _read_game(path, settings, cache, key, colors.get(path.name, ""))
        if progress is not None:
            progress(done, len(paths))
        if game.error:
            skipped.append(SkippedGame(path.name, REASON_CANNOT_READ, game.error))
            continue
        if game.result.reason:
            skipped.append(SkippedGame(path.name, game.result.reason))
        problems.extend(game.result.problems)
    if cache is not None:
        _finish_cache(cache, folder, paths)
    return problems, skipped


def _read_game(
    path: Path, settings: ExtractSettings, cache: ProblemCache | None, key: str, recorded_color: str
) -> CachedFile:
    """Return the problems of one file: from the cache if the file has not changed, else by reading it.

    The recorded color is part of the cache key, so giving or changing it makes the file read again.
    """
    key = f"{key}\ncolor={recorded_color}"
    try:
        stamp = FileStamp.of(path)
    except OSError as error:
        return CachedFile(ExtractResult(None), str(error))
    if cache is not None:
        try:
            cached = cache.get(path, stamp, key)
        except sqlite3.Error:
            cached = None  # A problem with the cache only means that the file is read.
        if cached is not None:
            return cached
    try:
        game = CachedFile(extract_problems(load_game(path), str(path), settings, recorded_color))
    except Exception as error:  # A broken file must not stop the other files.
        game = CachedFile(ExtractResult(None), str(error))
    if cache is not None:
        try:
            cache.put(path, stamp, key, game)
        except sqlite3.Error:
            pass  # The file is simply read again next time.
    return game


def _finish_cache(cache: ProblemCache, folder: Path, paths: list[Path]) -> None:
    """Remove files that are gone from the cache, and write the changes."""
    try:
        cache.forget_others(folder, paths)
        cache.commit()
    except sqlite3.Error:
        pass  # Only a cache: the files are read again next time.
