"""Analyze the games of a folder with KataGo and write the analysis into them (see the analysis package).

The command line (analysis_cli) and the top screen's "KataGoで棋譜解析" (gui.analysis_start) both use this module.
Each game file is copied to the backup folder before it is written.

The command line analyzes the games given to it (analyze_games): a game whose nodes all have
analysis data is skipped, as in KaTrain. A game analyzed by KaTrain (it has no KGM[KentoGo]) is skipped too, unless the user says yes to
analyzing it again for KentoGo (redo_kentogo): then KentoGo reads every position itself and writes
its own analysis data (KGA); KaTrain's analysis data (KT) is left as it is (see analysis.game_analysis).

The settings screen lists the games of the folder (list_games) and the user checks the ones to
analyze (see gui.analysis_chooser); every checked game is analyzed (analyze_chosen_games), whatever
analysis it has. The games analyzed by KentoGo are not listed until the user asks for them, and
only the games not analyzed yet are checked at first.
What happens is told to a listener: the start of each game, the progress of its steps, and how it ended.
A run can be stopped: it stops after the game that is being analyzed.
How long each game took, step by step, is told on the console and kept in a log (see analysis_timing).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pysgf import GoNode

from kentogo.analysis.analyze import DeepTargets, analyze_game, first_visits
from kentogo.analysis.game_analysis import Engine, EngineValues, GameAnalysis
from kentogo.analysis.saving import back_up, backup_folder, write_game
from kentogo.analysis.sgf_writer import WriteSettings, write_analysis
from kentogo.analysis_timing import GameTiming, StepClock, log_timing, timing_record
from kentogo.app_settings import AppSettings
from kentogo.common.sgf import load_game
from kentogo.common.types import opponent
from kentogo.engines import Engines, analysis_engine
from kentogo.mistakes.selection import Selection
from kentogo.record.katrain_kt import KENTOGO_MODE, KENTOGO_MODE_PROPERTY
from kentogo.record.kentogo_analysis import has_analysis
from kentogo.record.players import detect_my_color
from kentogo.version import app_version

# How the analysis of one game ended.
WRITTEN = "written"  # Analyzed and written (some nodes may have failed: see the detail).
SKIPPED = "skipped"  # Every node already had analysis data.
FAILED = "failed"  # The game could not be read or written.

DETECTION_SHARE = 0.5  # A move is read deeply when it lost this share of a problem's loss (see deep_targets).


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


# What a game of the folder is, for the list of the games to analyze (see list_games).
GAME_NEW = "new"  # Some nodes have no analysis data.
GAME_KATRAIN = "katrain"  # Every node has analysis data, but not from KentoGo (no KGM[KentoGo]): KaTrain's.
GAME_KENTOGO = "kentogo"  # Analyzed by KentoGo.
GAME_BROKEN = "broken"  # The file cannot be read.


@dataclass(frozen=True)
class FolderGame:
    """A game of the folder of the analysis, in the list of the games to analyze.

    Attributes:
        path: The SGF file.
        state: GAME_NEW, GAME_KATRAIN, GAME_KENTOGO or GAME_BROKEN.
    """

    path: Path
    state: str

    def checked_first(self) -> bool:
        """True if the game is checked when the list is shown.

        A game not analyzed yet is checked, and so is a file that cannot be read (its run tells why).
        A game analyzed by KaTrain or by KentoGo is not.
        """
        return self.state in (GAME_NEW, GAME_BROKEN)


@dataclass(frozen=True)
class FolderGames:
    """The games of the folder of the analysis, shown to the user before a run.

    Attributes:
        folder: The folder of the games, or None when no folder is set.
        backup: The folder where the games are copied before they are written.
        games: The SGF files of the folder, in the order of their names.
    """

    folder: Path | None
    backup: Path | None = None
    games: tuple[FolderGame, ...] = ()

    @property
    def without_kentogo(self) -> tuple[FolderGame, ...]:
        """The games that are listed at first: all but those analyzed by KentoGo."""
        return tuple(game for game in self.games if game.state != GAME_KENTOGO)

    @property
    def kentogo_count(self) -> int:
        """How many games were analyzed by KentoGo (listed only when the user asks for them)."""
        return len(self.games) - len(self.without_kentogo)


class GameChoice:
    """Which games of the list are checked, while the games analyzed by KentoGo are hidden or shown.

    A check is kept when a game is hidden and shown again, but only the checked games that are
    listed are chosen.
    """

    def __init__(self, games: FolderGames):
        """Start with the games checked as FolderGame.checked_first says, and the games analyzed by KentoGo hidden."""
        self.games = games
        self.with_kentogo = False
        self._checked = {game.path: game.checked_first() for game in games.games}

    def listed(self) -> tuple[FolderGame, ...]:
        """Return the games that are listed now."""
        return self.games.games if self.with_kentogo else self.games.without_kentogo

    def is_checked(self, game: FolderGame) -> bool:
        """True if the game is checked."""
        return self._checked[game.path]

    def set_checked(self, game: FolderGame, checked: bool) -> None:
        """Check or uncheck a game."""
        self._checked[game.path] = checked

    def set_all_listed(self, checked: bool) -> None:
        """Check or uncheck all the games that are listed now."""
        for game in self.listed():
            self._checked[game.path] = checked

    def chosen(self) -> list[Path]:
        """Return the games to analyze: the checked games that are listed, in the order of the list."""
        return [game.path for game in self.listed() if self._checked[game.path]]


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


def list_games(settings: AppSettings) -> FolderGames:
    """Return the games of the analysis's folder and what each one is (reading many games can take long)."""
    folder = games_folder(settings)
    if folder is None or not folder.is_dir():
        return FolderGames(folder)
    backup = backup_folder(folder, settings.analysis.backup_folder)
    return FolderGames(folder, backup, tuple(FolderGame(path, game_state(path)) for path in find_games([folder])))


def game_state(path: Path) -> str:
    """Return what a game file is: GAME_NEW, GAME_KATRAIN, GAME_KENTOGO or GAME_BROKEN."""
    try:
        root = load_game(path)
    except Exception:  # A broken file is listed: its run tells why it cannot be read.
        return GAME_BROKEN
    if not is_analyzed(root):
        return GAME_NEW
    return GAME_KENTOGO if analyzed_by_kentogo(root) else GAME_KATRAIN


def needs_kentogo_analysis(root: GoNode) -> bool:
    """True if the game is analyzed, but by KaTrain (it has no KGM[KentoGo]).

    Such a game is skipped unless the user says yes to analyzing it again for KentoGo.
    """
    return is_analyzed(root) and not analyzed_by_kentogo(root)


def analyzed_by_kentogo(root: GoNode) -> bool:
    """True if KentoGo wrote the analysis of the game (its root has KGM[KentoGo])."""
    return root.get_property(KENTOGO_MODE_PROPERTY, "") == KENTOGO_MODE


def is_analyzed(root: GoNode) -> bool:
    """True if every node of the game has analysis data (KentoGo's KGA or KaTrain's KT)."""
    return all(has_analysis(node) for node in root.nodes_in_tree)


def engine_values(settings: AppSettings) -> EngineValues:
    """Return the engine settings that the analysis uses (the visits, the noise and KaTrain's time limit)."""
    return EngineValues(settings.engine.max_visits, settings.engine.wide_root_noise, settings.engine.max_time)


def deep_targets(settings: AppSettings, root: GoNode, path: Path) -> DeepTargets:
    """Return which moves of a game are read deeply: those that can become problems with the quiz settings.

    The user's moves that lost at least the smallest loss of a problem, and the opponent's moves that lost
    at least the loss of a punishment chance when the user's reply did not punish them (it lost at least
    the quiz's punish_my_loss), but not in a position where the game was already decided (the quiz's
    decided winrate and lead; in a game with handicap stones, the lead gained since the start, see
    common.handicap); at most the analysis's deep_max_moves of them, the opponent's moves at
    most half of them (see analysis.analyze.chosen_deep_candidates). When the user's color is not found
    from the names, the moves of both colors are taken as the user's.

    The losses of the first analysis are rough (it reads few visits), so a move is read deeply already when
    it lost DETECTION_SHARE of those losses: a mistake that the first analysis found a little smaller is not
    missed (DeepTargets.read_share). The deep reading then gives its loss, and only a move that lost the whole
    loss can become a problem (the game's problem_nodes).
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
    theirs = extract.punish_opponent_loss
    losses = {"B": mine, "W": mine} if color is None else {color: mine, opponent(color): theirs}
    visits = settings.analysis.deep_visits or settings.engine.max_visits
    mine = frozenset({"B", "W"} if color is None else {color})
    decided = Selection.from_quiz(extract).is_decided
    handicap = bool(root.get_list_property("AB", []) or root.get_list_property("AW", []))
    return DeepTargets(
        losses,
        visits,
        decided,
        settings.analysis.deep_max_moves,
        mine,
        extract.punish_my_loss,
        handicap,
        DETECTION_SHARE,
    )


def write_settings() -> WriteSettings:
    """Return what the writing of the analysis needs: KentoGo's version."""
    return WriteSettings(app_version() or "dev")


def analyze_games(
    engine: Engine,
    games: list[Path],
    settings: AppSettings,
    listener: AnalysisListener,
    stop: threading.Event | None = None,
    redo_kentogo: bool = False,
) -> AnalysisSummary:
    """Analyze the games one by one with a KataGo that is ready, and write them; the analyzed ones are skipped.

    Args:
        engine: KataGo, ready to answer.
        games: The SGF files.
        settings: All settings (the analysis and the engine's visits and noise).
        listener: Told what happens.
        stop: When it is set, the run stops after the game that is being analyzed.
        redo_kentogo: Analyze again for KentoGo the games for which needs_kentogo_analysis is True (the user said yes).
    """
    write = write_settings()
    return _analyze_each(
        games, listener, stop, lambda path: analyze_one(engine, path, settings, listener, write, redo_kentogo)
    )


def analyze_chosen_games(
    engine: Engine,
    games: list[Path],
    settings: AppSettings,
    listener: AnalysisListener,
    stop: threading.Event | None = None,
) -> AnalysisSummary:
    """Analyze and write every game given (the user chose them), whatever analysis it has already.

    The arguments are those of analyze_games.
    """
    write = write_settings()
    return _analyze_each(games, listener, stop, lambda path: analyze_chosen(engine, path, settings, listener, write))


def _analyze_each(
    games: list[Path],
    listener: AnalysisListener,
    stop: threading.Event | None,
    analyze: Callable[[Path], tuple[str, str, int]],
) -> AnalysisSummary:
    """Analyze the games one by one with analyze (it returns what analyze_one returns), telling the listener."""
    summary = AnalysisSummary()
    for number, path in enumerate(games, 1):
        if stop is not None and stop.is_set():
            summary.stopped = True
            break
        listener.game_started(number, len(games), path.name)
        outcome, detail, failed_nodes = analyze(path)
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
    """Analyze one game, back it up and write it; skip it when it is analyzed (see analyze_games for redo_kentogo).

    Returns:
        (outcome, detail, the number of nodes that KataGo could not analyze).
    """
    try:
        root = load_game(path)
    except Exception as error:  # A broken file must not stop the others.
        return FAILED, f"cannot be read: {error}", 0
    if is_analyzed(root) and not (redo_kentogo and needs_kentogo_analysis(root)):
        return SKIPPED, "every node already has analysis data", 0
    return _analyze_and_write(engine, path, root, settings, listener, write)


def analyze_chosen(
    engine: Engine, path: Path, settings: AppSettings, listener: AnalysisListener, write: WriteSettings
) -> tuple[str, str, int]:
    """Analyze one game that the user chose, back it up and write it (it is never skipped).

    Returns:
        (outcome, detail, the number of nodes that KataGo could not analyze).
    """
    try:
        root = load_game(path)
    except Exception as error:  # A broken file must not stop the others.
        return FAILED, f"cannot be read: {error}", 0
    return _analyze_and_write(engine, path, root, settings, listener, write)


def _analyze_and_write(
    engine: Engine, path: Path, root: GoNode, settings: AppSettings, listener: AnalysisListener, write: WriteSettings
) -> tuple[str, str, int]:
    """Analyze a game that has been read, back up its file and write it (returns what analyze_one returns).

    How long it took is told and kept (see analysis_timing).
    """
    analysis = settings.analysis
    size_before = path.stat().st_size if path.exists() else 0
    clock = StepClock()
    targets = deep_targets(settings, root, path)
    game = analyze_game(engine, root, analysis, engine_values(settings), _both(listener.progress, clock), targets)
    analyzed = clock.clock()
    visits = (_first_visits(settings), targets.visits)
    write_analysis(game, write)
    try:
        copy = back_up(path, backup_folder(path.parent, analysis.backup_folder), datetime.now())
        write_game(path, root.sgf())
    except OSError as error:
        _log(path, FAILED, clock, analyzed, game, visits, (size_before, 0), write.version)
        return FAILED, f"cannot be written: {error}", game.failed
    seconds = _log(path, WRITTEN, clock, analyzed, game, visits, (size_before, path.stat().st_size), write.version)
    detail = f"written in {seconds:.0f} s (backup: {copy})" + _failures(game)
    return WRITTEN, detail, game.failed


def _both(progress: Callable[[str, int, int], None], clock: StepClock) -> Callable[[str, int, int], None]:
    """Return a progress that tells the listener and the clock."""

    def both(step: str, done: int, total: int) -> None:
        clock.progress(step, done, total)
        progress(step, done, total)

    return both


def _log(
    path: Path,
    outcome: str,
    clock: StepClock,
    analyzed: float,
    game: GameAnalysis,
    visits: tuple[int, int],
    sizes: tuple[int, int],
    version: str,
) -> float:
    """Tell and keep how long a game took (see analysis_timing). Returns its seconds in all."""
    timing = GameTiming(path.name, outcome, clock, analyzed, clock.clock(), game, visits, sizes, version)
    record = timing_record(timing, datetime.now())
    log_timing(record)
    return record["seconds"]["total"]


def _first_visits(settings: AppSettings) -> int:
    """Return the visits of each position in the first analysis (see analysis.analyze.first_visits)."""
    return first_visits(settings.analysis)


def _failures(game: GameAnalysis) -> str:
    """Return the text about the nodes that KataGo could not analyze, or ""."""
    if not game.failed:
        return ""
    moves = ", ".join(str(node.depth) for node in game.failed_nodes)
    return f"; {game.failed} nodes could not be analyzed (after move: {moves})"


def run_analysis(
    settings: AppSettings,
    running: Engines | None,
    games: list[Path],
    listener: AnalysisListener,
    stop: threading.Event | None = None,
) -> AnalysisSummary:
    """Analyze the games that the user chose, with the app's KataGo when it runs with the settings.

    Otherwise a KataGo of its own is started for the run and stopped after it.

    Args:
        settings: All settings.
        running: The app's KataGo, or None.
        games: The chosen SGF files (see list_games).
        listener: Told what happens.
        stop: When it is set, the run stops after the game that is being analyzed.
    """
    if not games:
        return AnalysisSummary(problem="no games chosen")
    engine, own, problem = analysis_engine(settings.engine, running)
    if engine is None or not engine.wait_until_ready(settings.engine.ready_timeout):
        if engine is not None and own:
            engine.close()
        return AnalysisSummary(problem=problem or "KataGo did not get ready")
    try:
        return analyze_chosen_games(engine, games, settings, listener, stop)
    finally:
        if own:
            engine.close()
