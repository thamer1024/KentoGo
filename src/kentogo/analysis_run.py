"""Analyze the games of a folder with KataGo and write the analysis into them (see the analysis package).

The command line (analysis_cli) and the settings screen's "棋譜を解析" button both use this module.
Each game file is copied to the backup folder before it is written. A game whose nodes all have
analysis data is skipped, unless it is analyzed again (the setting reanalyze), as in KaTrain.
What happens is told to a listener: the start of each game, the progress of its steps, and how it ended.
A run can be stopped: it stops after the game that is being analyzed.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pysgf import GoNode

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.game_analysis import Engine, EngineValues, GameAnalysis, analyze_game
from kentogo.analysis.rules import rules_for
from kentogo.analysis.saving import back_up, backup_folder, write_game
from kentogo.analysis.sgf_writer import WriteSettings, write_analysis
from kentogo.app_settings import AppSettings
from kentogo.common.sgf import load_game
from kentogo.engines import Engines, analysis_engine
from kentogo.version import app_version

READY_TIMEOUT = 600  # Seconds to wait for KataGo to load its model.

# How the analysis of one game ended.
WRITTEN = "written"  # Analyzed and written (some nodes may have failed: see the detail).
SKIPPED = "skipped"  # Every node already had analysis data.
FAILED = "failed"  # The game could not be read or written.


@dataclass(frozen=True)
class AnalysisListener:
    """What is told while the games are analyzed. The calls come from other threads.

    Attributes:
        game_started: (number of the game from 1, number of games, file name).
        progress: (step, answers received, queries sent) of the game (see analysis.game_analysis).
        game_finished: (file name, outcome: WRITTEN, SKIPPED or FAILED, a detail in English).
    """

    game_started: Callable[[int, int, str], None]
    progress: Callable[[str, int, int], None]
    game_finished: Callable[[str, str, str], None]


@dataclass
class AnalysisSummary:
    """How many games ended in each way, and whether the run was stopped.

    Attributes:
        outcomes: The number of games for each outcome (WRITTEN, SKIPPED, FAILED).
        failed_nodes: The number of nodes that KataGo could not analyze, in all games.
        incomplete: The number of games written with nodes that KataGo could not analyze.
        stopped: True if the run was stopped before the last game.
        problem: Why nothing could be analyzed (no games, KataGo not started), or "".
    """

    outcomes: dict[str, int] = field(default_factory=lambda: {WRITTEN: 0, SKIPPED: 0, FAILED: 0})
    failed_nodes: int = 0
    incomplete: int = 0
    stopped: bool = False
    problem: str = ""


@dataclass(frozen=True)
class AnalysisPlan:
    """What a run would do, shown to the user before it starts.

    Attributes:
        folder: The folder of the games, or None when no folder is set.
        backup: The folder where the games are copied before they are written.
        games: The number of SGF files in the folder.
        analyzed: How many of them have analysis data on every node (skipped unless reanalyze).
        reanalyze: True if the analyzed games are analyzed again.
    """

    folder: Path | None
    backup: Path | None = None
    games: int = 0
    analyzed: int = 0
    reanalyze: bool = False

    @property
    def to_analyze(self) -> int:
        """The number of games that the run would analyze."""
        return self.games if self.reanalyze else self.games - self.analyzed


def games_folder(settings: AppSettings) -> Path | None:
    """Return the folder of the games to analyze: the analysis's own, or the games folder of the quiz."""
    text = settings.analysis.games_folder or settings.quiz.games_folder
    return Path(text).expanduser() if text else None


def find_games(paths: list[Path]) -> list[Path]:
    """Return the SGF files given, and the SGF files in the folders given (not in their subfolders)."""
    games = []
    for path in paths:
        path = path.expanduser()
        games += sorted(path.glob("*.sgf")) if path.is_dir() else [path]
    return games


def plan_analysis(settings: AppSettings) -> AnalysisPlan:
    """Return what a run with these settings would do: the folders and the number of games (a file
    that cannot be read counts as not analyzed: the run tells it)."""
    folder = games_folder(settings)
    if folder is None or not folder.is_dir():
        return AnalysisPlan(folder)
    games = find_games([folder])
    analyzed = sum(_is_analyzed_file(path) for path in games)
    backup = backup_folder(folder, settings.analysis.backup_folder)
    return AnalysisPlan(folder, backup, len(games), analyzed, settings.analysis.reanalyze)


def _is_analyzed_file(path: Path) -> bool:
    try:
        return is_analyzed(load_game(path))
    except Exception:  # A broken file is counted with the games to analyze.
        return False


def is_analyzed(root: GoNode) -> bool:
    """True if every node of the game has analysis data."""
    return all(node.get_list_property("KT", []) for node in root.nodes_in_tree)


def engine_values(settings: AppSettings) -> EngineValues:
    """Return the engine settings that the analysis uses."""
    return EngineValues(settings.engine.max_visits, settings.engine.wide_root_noise)


def write_settings(analysis: AnalysisSettings) -> WriteSettings:
    """Return what the writing of the analysis needs: the settings, KentoGo's version and the mode's rules."""
    return WriteSettings(analysis, app_version() or "dev", rules_for(analysis))


def analyze_games(
    engine: Engine,
    games: list[Path],
    settings: AppSettings,
    listener: AnalysisListener,
    stop: threading.Event | None = None,
) -> AnalysisSummary:
    """Analyze the games one by one with a KataGo that is ready, and write them.

    Args:
        engine: KataGo, ready to answer.
        games: The SGF files.
        settings: All settings (the analysis and the engine's visits and noise).
        listener: Told what happens.
        stop: When it is set, the run stops after the game that is being analyzed.
    """
    summary = AnalysisSummary()
    write = write_settings(settings.analysis)
    for number, path in enumerate(games, 1):
        if stop is not None and stop.is_set():
            summary.stopped = True
            break
        listener.game_started(number, len(games), path.name)
        outcome, detail, failed_nodes = analyze_one(engine, path, settings, listener, write)
        summary.outcomes[outcome] += 1
        summary.failed_nodes += failed_nodes
        summary.incomplete += outcome == WRITTEN and failed_nodes > 0
        listener.game_finished(path.name, outcome, detail)
    return summary


def analyze_one(
    engine: Engine, path: Path, settings: AppSettings, listener: AnalysisListener, write: WriteSettings
) -> tuple[str, str, int]:
    """Analyze one game, back it up and write it.

    Returns:
        (outcome, detail, the number of nodes that KataGo could not analyze).
    """
    analysis = settings.analysis
    try:
        root = load_game(path)
    except Exception as error:  # A broken file must not stop the others.
        return FAILED, f"cannot be read: {error}", 0
    if is_analyzed(root) and not analysis.reanalyze:
        return SKIPPED, "every node already has analysis data", 0
    started = time.monotonic()
    game = analyze_game(engine, root, analysis, engine_values(settings), listener.progress, write.rules)
    write_analysis(game, write)
    try:
        copy = back_up(path, backup_folder(path.parent, analysis.backup_folder), datetime.now())
        write_game(path, root.sgf())
    except OSError as error:
        return FAILED, f"cannot be written: {error}", game.failed
    detail = f"written in {time.monotonic() - started:.0f} s (backup: {copy})" + _failures(game)
    return WRITTEN, detail, game.failed


def _failures(game: GameAnalysis) -> str:
    """Return the text about the nodes that KataGo could not analyze, or ""."""
    if not game.failed:
        return ""
    moves = ", ".join(str(node.depth) for node in game.failed_nodes)
    return f"; {game.failed} nodes could not be analyzed (after move: {moves})"


def run_folder_analysis(
    settings: AppSettings, running: Engines | None, listener: AnalysisListener, stop: threading.Event | None = None
) -> AnalysisSummary:
    """Analyze the games of the analysis's folder, with the app's KataGo when it runs with the settings.

    Otherwise a KataGo of its own is started for the run and stopped after it.

    Args:
        settings: All settings.
        running: The app's KataGo, or None.
        listener: Told what happens.
        stop: When it is set, the run stops after the game that is being analyzed.
    """
    folder = games_folder(settings)
    games = find_games([folder]) if folder is not None else []
    if not games:
        return AnalysisSummary(problem="no games: set the games folder")
    engine, own, problem = analysis_engine(settings.engine, running)
    if engine is None or not engine.wait_until_ready(READY_TIMEOUT):
        if engine is not None and own:
            engine.close()
        return AnalysisSummary(problem=problem or "KataGo did not get ready")
    try:
        return analyze_games(engine, games, settings, listener, stop)
    finally:
        if own:
            engine.close()
