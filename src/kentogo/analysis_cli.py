"""A command line that analyzes games with KataGo and writes the analysis into them, as KaTrain does.

It is for checking the analysis before its screens are made. The settings come from the
"analysis" part of the settings file, and the options below replace them for one run:

    uv run python -m kentogo.analysis_cli                       # the games folder of the settings
    uv run python -m kentogo.analysis_cli GAME.sgf FOLDER ...   # some games or folders
    uv run python -m kentogo.analysis_cli --dry-run             # only tell what would be done
    uv run python -m kentogo.analysis_cli --reanalyze --mistakes-only --visits 2000

Each game file is copied to the backup folder before it is written. A game whose nodes all
have analysis data is skipped, unless it is analyzed again (--reanalyze), as in KaTrain.
The progress is shown on the console.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
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
from kentogo.engines import start_engine
from kentogo.settings_file import SETTINGS_PATH, load_settings
from kentogo.version import app_version

READY_TIMEOUT = 600  # Seconds to wait for KataGo to load its model.
STEP_NAMES = {"first": "analysis", "again": "re-analysis"}


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(prog="python -m kentogo.analysis_cli", description=__doc__.splitlines()[0])
    parser.add_argument("paths", type=Path, nargs="*", help="SGF files or folders (default: the games folder)")
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH, help="the settings file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compatible", dest="compatible", action="store_const", const=True, help="exactly as KaTrain")
    mode.add_argument("--improved", dest="compatible", action="store_const", const=False, help="KentoGo's mode")
    parser.add_argument("--fast", action="store_true", default=None, help="analyze first with fast_visits")
    parser.add_argument("--reanalyze", action="store_true", default=None, help="analyze again (KaTrain's re-analysis)")
    parser.add_argument("--mistakes-only", action="store_true", default=None, help="analyze again only the mistakes")
    parser.add_argument("--from", dest="move_from", type=int, help="analyze again from this move")
    parser.add_argument("--to", dest="move_to", type=int, help="analyze again up to this move")
    parser.add_argument("--visits", type=int, help="the visits of the re-analysis")
    parser.add_argument("--backup", help="the backup folder")
    parser.add_argument("--dry-run", action="store_true", help="only tell what would be done")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the command. Returns the exit code (0 when every game was analyzed or skipped)."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")  # A Windows console may not show all characters.
    arguments = parse_arguments(argv)
    settings = load_settings(arguments.settings)
    try:
        analysis = settings_with_options(settings.analysis, arguments)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    folder = games_folder(settings, analysis)
    games = find_games(arguments.paths or ([folder] if folder else []))
    if not games:
        print("No games: give SGF files or folders, or set the games folder.", file=sys.stderr)
        return 2
    if arguments.dry_run:
        return show_plan(games, analysis)
    return analyze_all(games, settings, analysis)


def settings_with_options(settings: AnalysisSettings, arguments: argparse.Namespace) -> AnalysisSettings:
    """Return the settings of the analysis with the options of the command line in place of them.

    Raises:
        ValueError: If a value is not allowed.
    """
    options = {
        "katrain_compatible": arguments.compatible,
        "fast": arguments.fast,
        "reanalyze": arguments.reanalyze,
        "mistakes_only": arguments.mistakes_only,
        "move_from": arguments.move_from,
        "move_to": arguments.move_to,
        "reanalyze_visits": arguments.visits,
        "backup_folder": arguments.backup,
    }
    changed = replace(settings, **{key: value for key, value in options.items() if value is not None})
    if arguments.mistakes_only or arguments.move_from or arguments.move_to or arguments.visits is not None:
        changed = replace(changed, reanalyze=True)  # These options are about the re-analysis.
    changed.check()
    return changed


def games_folder(settings: AppSettings, analysis: AnalysisSettings) -> Path | None:
    """Return the games folder: the one of the analysis, or the games folder of the quiz."""
    text = analysis.games_folder or settings.quiz.games_folder
    return Path(text).expanduser() if text else None


def find_games(paths: list[Path]) -> list[Path]:
    """Return the SGF files given, and the SGF files in the folders given (not in their subfolders)."""
    games = []
    for path in paths:
        path = path.expanduser()
        games += sorted(path.glob("*.sgf")) if path.is_dir() else [path]
    return games


def show_plan(games: list[Path], analysis: AnalysisSettings) -> int:
    """Tell, for each game, how many nodes it has and how many already have analysis data."""
    for number, path in enumerate(games, 1):
        try:
            root = load_game(path)
        except Exception as error:  # A broken file must not stop the others.
            print(f"[{number}/{len(games)}] {path.name}: cannot be read: {error}")
            continue
        nodes = root.nodes_in_tree
        saved = sum(1 for node in nodes if node.get_list_property("KT", []))
        action = "skip (analyzed)" if is_analyzed(root) and not analysis.reanalyze else "analyze"
        print(f"[{number}/{len(games)}] {path.name}: {len(nodes)} nodes, {saved} with analysis data -> {action}")
    return 0


def is_analyzed(root: GoNode) -> bool:
    """True if every node of the game has analysis data."""
    return all(node.get_list_property("KT", []) for node in root.nodes_in_tree)


def analyze_all(games: list[Path], settings: AppSettings, analysis: AnalysisSettings) -> int:
    """Start KataGo, analyze the games one by one, and stop KataGo."""
    print("Starting KataGo...", flush=True)
    engine, _, problem = start_engine(settings.engine)
    if engine is None or not engine.wait_until_ready(READY_TIMEOUT):
        print(f"KataGo could not be started: {problem or (engine.error_output() if engine else '')}", file=sys.stderr)
        return 1
    values = EngineValues(settings.engine.max_visits, settings.engine.wide_root_noise)
    write = WriteSettings(analysis, app_version() or "dev", rules_for(analysis))
    print(f"Mode: {'KaTrain compatible' if analysis.katrain_compatible else 'KentoGo'}", flush=True)
    failed = 0
    try:
        for number, path in enumerate(games, 1):
            print(f"[{number}/{len(games)}] {path.name}", flush=True)
            backups = backup_folder(path.parent, analysis.backup_folder)
            failed += not analyze_one(engine, path, analysis, values, write, backups)
    finally:
        engine.close()
    print(f"Done: {len(games) - failed} of {len(games)} games without problems.")
    return 1 if failed else 0


def analyze_one(
    engine: Engine, path: Path, analysis: AnalysisSettings, values: EngineValues, write: WriteSettings, backups: Path
) -> bool:
    """Analyze one game, back it up and write it. Returns False when something went wrong."""
    try:
        root = load_game(path)
    except Exception as error:  # A broken file must not stop the others.
        print(f"  cannot be read: {error}")
        return False
    if is_analyzed(root) and not analysis.reanalyze:
        print("  skipped: every node already has analysis data")
        return True
    started = time.monotonic()
    game = analyze_game(engine, root, analysis, values, show_progress, write.rules)
    write_analysis(game, write)
    try:
        copy = back_up(path, backups, datetime.now())
        write_game(path, root.sgf())
    except OSError as error:
        print(f"  cannot be written: {error}")
        return False
    print(f"  written in {time.monotonic() - started:.0f} s (backup: {copy})")
    return report_failures(game)


def report_failures(game: GameAnalysis) -> bool:
    """Tell how many nodes KataGo could not analyze. Returns True when there were none."""
    if game.failed:
        moves = ", ".join(str(node.depth) for node in game.failed_nodes)
        print(f"  {game.failed} nodes could not be analyzed (after move: {moves})")
    return not game.failed


def show_progress(step: str, done: int, total: int) -> None:
    """Show the progress of a step on one line of the console (called in KataGo's thread)."""
    print(f"\r  {STEP_NAMES.get(step, step)}: {done}/{total} nodes", end="\n" if done == total else "", flush=True)


if __name__ == "__main__":
    sys.exit(main())
