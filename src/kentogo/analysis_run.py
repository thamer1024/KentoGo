"""Analyze the games of a folder with KataGo and write the analysis into them (see the analysis package).

The command line (analysis_cli) and the settings screen's "KataGoで棋譜を解析" button both use this module.
Each game file is copied to the backup folder before it is written. A game whose nodes all have
analysis data is skipped, unless it is analyzed again (the setting reanalyze), as in KaTrain.
A game analyzed by KaTrain (it has no KGM[KentoGo]) is skipped too, unless the user says yes to
analyzing it again for KentoGo (redo_kentogo): then its saved analysis is kept, and the played moves
are read and written in KentoGo's way (see analysis.played_moves).
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

from kentogo.analysis.analysis_settings import DEEP_FACTOR, AnalysisSettings
from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.game_analysis import Engine, EngineValues, GameAnalysis
from kentogo.analysis.saving import back_up, backup_folder, write_game
from kentogo.analysis.sgf_writer import WriteSettings, write_analysis
from kentogo.app_settings import AppSettings
from kentogo.common.sgf import load_game
from kentogo.common.types import opponent
from kentogo.engines import Engines, analysis_engine
from kentogo.mistakes.selection import Selection
from kentogo.record.katrain_kt import KENTOGO_MODE, KENTOGO_MODE_PROPERTY
from kentogo.record.players import detect_my_color
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
        kentogo_redo: How many of the analyzed games were analyzed by KaTrain and could be analyzed again for KentoGo
            (see needs_kentogo_analysis); the user is asked about them.
    """

    folder: Path | None
    backup: Path | None = None
    games: int = 0
    analyzed: int = 0
    reanalyze: bool = False
    kentogo_redo: int = 0

    def count(self, redo_kentogo: bool = False) -> int:
        """The number of games that the run would analyze (with the games for KentoGo if redo_kentogo)."""
        if self.reanalyze:
            return self.games
        return self.games - self.analyzed + (self.kentogo_redo if redo_kentogo else 0)


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
    states = [_analyzed_state(path, settings.analysis) for path in games]
    backup = backup_folder(folder, settings.analysis.backup_folder)
    analyzed = sum(state[0] for state in states)
    redo = sum(state[1] for state in states)
    return AnalysisPlan(folder, backup, len(games), analyzed, settings.analysis.reanalyze, redo)


def _analyzed_state(path: Path, analysis: AnalysisSettings) -> tuple[bool, bool]:
    """Return (analyzed, can be analyzed again for KentoGo) of a game file."""
    try:
        root = load_game(path)
    except Exception:  # A broken file is counted with the games to analyze.
        return False, False
    return is_analyzed(root), needs_kentogo_analysis(root, analysis)


def needs_kentogo_analysis(root: GoNode, analysis: AnalysisSettings) -> bool:
    """True if the game is analyzed, but by KaTrain (it has no KGM[KentoGo]).

    Such a game is skipped unless the user says yes to analyzing it again for KentoGo.
    With reanalyze, every game is analyzed again anyway, so this is False.
    """
    if analysis.reanalyze or not is_analyzed(root):
        return False
    return root.get_property(KENTOGO_MODE_PROPERTY, "") != KENTOGO_MODE


def is_analyzed(root: GoNode) -> bool:
    """True if every node of the game has analysis data."""
    return all(node.get_list_property("KT", []) for node in root.nodes_in_tree)


def engine_values(settings: AppSettings) -> EngineValues:
    """Return the engine settings that the analysis uses."""
    return EngineValues(settings.engine.max_visits, settings.engine.wide_root_noise)


def deep_targets(settings: AppSettings, root: GoNode, path: Path) -> DeepTargets:
    """Return which moves of a game are read deeply: those that can become problems with the quiz settings.

    The user's moves that lost at least the smallest loss of a problem, and the opponent's moves that
    lost at least the loss of a punishment chance, but not in a position where the game was already
    decided (the quiz's decided winrate and lead). When the user's color is not found from the names,
    the moves of both colors are taken as the user's.
    """
    extract = settings.quiz.extract
    mine = extract.smallest_loss()
    color = detect_my_color(
        str(root.get_property("PB", "")),
        str(root.get_property("PW", "")),
        extract.my_names,
        ranks=(str(root.get_property("BR", "")), str(root.get_property("WR", ""))),
        file_name=str(path),
    )
    losses = {"B": mine, "W": mine} if color is None else {color: mine, opponent(color): extract.punish_opponent_loss}
    visits = settings.analysis.deep_visits or DEEP_FACTOR * settings.engine.max_visits
    return DeepTargets(losses, visits, Selection.from_quiz(extract).is_decided)


def write_settings(analysis: AnalysisSettings) -> WriteSettings:
    """Return what the writing of the analysis needs: the settings and KentoGo's version."""
    return WriteSettings(analysis, app_version() or "dev")


def analyze_games(
    engine: Engine,
    games: list[Path],
    settings: AppSettings,
    listener: AnalysisListener,
    stop: threading.Event | None = None,
    redo_kentogo: bool = False,
) -> AnalysisSummary:
    """Analyze the games one by one with a KataGo that is ready, and write them.

    Args:
        engine: KataGo, ready to answer.
        games: The SGF files.
        settings: All settings (the analysis and the engine's visits and noise).
        listener: Told what happens.
        stop: When it is set, the run stops after the game that is being analyzed.
        redo_kentogo: Analyze again for KentoGo the games for which needs_kentogo_analysis is True (the user said yes).
    """
    summary = AnalysisSummary()
    write = write_settings(settings.analysis)
    for number, path in enumerate(games, 1):
        if stop is not None and stop.is_set():
            summary.stopped = True
            break
        listener.game_started(number, len(games), path.name)
        outcome, detail, failed_nodes = analyze_one(engine, path, settings, listener, write, redo_kentogo)
        summary.outcomes[outcome] += 1
        summary.failed_nodes += failed_nodes
        summary.incomplete += outcome == WRITTEN and failed_nodes > 0
        listener.game_finished(path.name, outcome, detail)
    return summary


def analyze_one(
    engine: Engine,
    path: Path,
    settings: AppSettings,
    listener: AnalysisListener,
    write: WriteSettings,
    redo_kentogo: bool = False,
) -> tuple[str, str, int]:
    """Analyze one game, back it up and write it (see analyze_games for redo_kentogo).

    Returns:
        (outcome, detail, the number of nodes that KataGo could not analyze).
    """
    analysis = settings.analysis
    try:
        root = load_game(path)
    except Exception as error:  # A broken file must not stop the others.
        return FAILED, f"cannot be read: {error}", 0
    if is_analyzed(root) and not analysis.reanalyze and not (redo_kentogo and needs_kentogo_analysis(root, analysis)):
        return SKIPPED, "every node already has analysis data", 0
    started = time.monotonic()
    targets = deep_targets(settings, root, path)
    game = analyze_game(engine, root, analysis, engine_values(settings), listener.progress, targets)
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
    settings: AppSettings,
    running: Engines | None,
    listener: AnalysisListener,
    stop: threading.Event | None = None,
    redo_kentogo: bool = False,
) -> AnalysisSummary:
    """Analyze the games of the analysis's folder, with the app's KataGo when it runs with the settings.

    Otherwise a KataGo of its own is started for the run and stopped after it.

    Args:
        settings: All settings.
        running: The app's KataGo, or None.
        listener: Told what happens.
        stop: When it is set, the run stops after the game that is being analyzed.
        redo_kentogo: Analyze again for KentoGo the games analyzed by KaTrain (see analyze_games).
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
        return analyze_games(engine, games, settings, listener, stop, redo_kentogo)
    finally:
        if own:
            engine.close()
