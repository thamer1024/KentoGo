"""A command line that analyzes games with KataGo and writes the analysis into them, as KaTrain does.

It is for checking the analysis before its screens are made. The settings come from the
"analysis" part of the settings file, and the options below replace them for one run:

    uv run python -m kentogo.analysis_cli                       # the games folder of the settings
    uv run python -m kentogo.analysis_cli GAME.sgf FOLDER ...   # some games or folders
    uv run python -m kentogo.analysis_cli --dry-run             # only tell what would be done
    uv run python -m kentogo.analysis_cli --reanalyze --mistakes-only --visits 2000

Each game file is copied to the backup folder before it is written. A game whose nodes all
have analysis data is skipped, unless it is analyzed again (--reanalyze), as in KaTrain.
In KentoGo's mode, the games analyzed in KaTrain's way are counted first, and the user is asked
(y/n) whether they are analyzed again for KentoGo (see analysis_run.needs_kentogo_analysis).
The progress is shown on the console.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis_run import (
    FAILED,
    READY_TIMEOUT,
    SKIPPED,
    WRITTEN,
    AnalysisListener,
    analyze_games,
    find_games,
    games_folder,
    is_analyzed,
    needs_kentogo_analysis,
)
from kentogo.app_settings import AppSettings
from kentogo.common.sgf import load_game
from kentogo.engines import start_engine
from kentogo.settings_file import SETTINGS_PATH, load_settings

STEP_NAMES = {"first": "analysis", "again": "re-analysis", "played": "played moves"}
KENTOGO_QUESTION = (
    "KataGoで解析済みです（{count} 局。KentoGoの方法の解析ではありません）。KentoGo用にもう一度解析しますか？ y/n: "
)


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
    settings = replace(settings, analysis=analysis)
    folder = games_folder(settings)
    games = find_games(arguments.paths or ([folder] if folder else []))
    if not games:
        print("No games: give SGF files or folders, or set the games folder.", file=sys.stderr)
        return 2
    if arguments.dry_run:
        return show_plan(games, analysis)
    waiting = sum(_needs_kentogo_analysis(path, analysis) for path in games)
    return analyze_all(games, settings, bool(waiting) and ask_kentogo_redo(waiting))


def _needs_kentogo_analysis(path: Path, analysis: AnalysisSettings) -> bool:
    try:
        return needs_kentogo_analysis(load_game(path), analysis)
    except Exception:  # A broken file is told when it is analyzed.
        return False


def ask_kentogo_redo(count: int, ask: Callable[[str], str] | None = None) -> bool:
    """Ask whether the games analyzed in KaTrain's way are analyzed again for KentoGo (y or n).

    The question is asked again until the answer is y or n; without an answer (no console), it is n.
    ask reads the answer (by default, input on the console).
    """
    ask = ask or input
    while True:
        try:
            answer = ask(KENTOGO_QUESTION.format(count=count)).strip().lower()
        except EOFError:
            print()
            return False
        if answer in ("y", "yes", "n", "no"):
            return answer.startswith("y")


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
        if needs_kentogo_analysis(root, analysis):
            action = "ask (analyzed in KaTrain's way: analyze again for KentoGo?)"
        else:
            action = "skip (analyzed)" if is_analyzed(root) and not analysis.reanalyze else "analyze"
        print(f"[{number}/{len(games)}] {path.name}: {len(nodes)} nodes, {saved} with analysis data -> {action}")
    return 0


def analyze_all(games: list[Path], settings: AppSettings, redo_kentogo: bool = False) -> int:
    """Start KataGo, analyze the games one by one, and stop KataGo (see analysis_run.analyze_games for redo_kentogo)."""
    print("Starting KataGo...", flush=True)
    engine, _, problem = start_engine(settings.engine)
    if engine is None or not engine.wait_until_ready(READY_TIMEOUT):
        print(f"KataGo could not be started: {problem or (engine.error_output() if engine else '')}", file=sys.stderr)
        return 1
    print(f"Mode: {'KaTrain compatible' if settings.analysis.katrain_compatible else 'KentoGo'}", flush=True)
    listener = AnalysisListener(show_game, show_progress, show_outcome)
    try:
        summary = analyze_games(engine, games, settings, listener, redo_kentogo=redo_kentogo)
    finally:
        engine.close()
    good = summary.outcomes[WRITTEN] + summary.outcomes[SKIPPED] - summary.incomplete
    print(f"Done: {good} of {len(games)} games without problems.")
    return 1 if summary.outcomes[FAILED] or summary.incomplete else 0


def show_game(number: int, total: int, name: str) -> None:
    """Show which game is analyzed."""
    print(f"[{number}/{total}] {name}", flush=True)


def show_outcome(name: str, outcome: str, detail: str) -> None:
    """Show how the analysis of a game ended."""
    print(f"  {'skipped: ' if outcome == SKIPPED else ''}{detail}")


def show_progress(step: str, done: int, total: int) -> None:
    """Show the progress of a step on one line of the console (called in KataGo's thread)."""
    print(f"\r  {STEP_NAMES.get(step, step)}: {done}/{total} nodes", end="\n" if done == total else "", flush=True)


if __name__ == "__main__":
    sys.exit(main())
