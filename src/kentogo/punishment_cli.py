"""A command line that lists the moments when the opponent made a big mistake and the user did not punish it.

It is for checking the "punishment problems" before they are asked in the quiz:

    uv run python -m kentogo.punishment_cli                     # the games folder of the settings
    uv run python -m kentogo.punishment_cli GAME.sgf FOLDER ...
    uv run python -m kentogo.punishment_cli --opponent-loss 15 --my-loss 5

A moment counts when the opponent's move lost at least --opponent-loss points (default 10) and
the user's next move lost at least --my-loss points (default 5). "problem" marks the moments that
are already problems of the quiz (see mistakes.extract).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kentogo.common.sgf import load_game
from kentogo.mistakes.extract import PunishmentChance, extract_problems, punishment_chances
from kentogo.settings_file import SETTINGS_PATH, load_settings

OPPONENT_LOSS = 10.0
MY_LOSS = 5.0


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(prog="python -m kentogo.punishment_cli", description=__doc__.splitlines()[0])
    parser.add_argument("paths", type=Path, nargs="*", help="SGF files or folders (default: the games folder)")
    parser.add_argument("--opponent-loss", type=float, default=OPPONENT_LOSS, help="the opponent's smallest loss")
    parser.add_argument("--my-loss", type=float, default=MY_LOSS, help="the smallest loss of your move")
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH, help="the settings file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the command. Returns the exit code (0 when the games could be read)."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")  # A Windows console may not show all characters.
    arguments = parse_arguments(argv)
    settings = load_settings(arguments.settings)
    folder = settings.quiz.games_folder
    games = find_games(arguments.paths or ([Path(folder).expanduser()] if folder else []))
    if not games:
        print("No games: give SGF files or folders, or set the games folder.", file=sys.stderr)
        return 2
    total = 0
    for path in games:
        try:
            root = load_game(path)
        except Exception as error:  # A broken file must not stop the others.
            print(f"{path.name}: cannot be read: {error}")
            continue
        chances = punishment_chances(root, str(path), settings.quiz.extract, arguments.opponent_loss, arguments.my_loss)
        problems = {
            problem.move_number for problem in extract_problems(root, str(path), settings.quiz.extract).problems
        }
        total += len(chances)
        show_game(path, chances, problems)
    print(f"Done: {total} moments in {len(games)} games.")
    return 0


def find_games(paths: list[Path]) -> list[Path]:
    """Return the SGF files given, and the SGF files in the folders given (not in their subfolders)."""
    games = []
    for path in paths:
        path = path.expanduser()
        games += sorted(path.glob("*.sgf")) if path.is_dir() else [path]
    return games


def show_game(path: Path, chances: list[PunishmentChance], problems: set[int]) -> None:
    """Show the moments of one game, one line each."""
    if not chances:
        return
    print(path.name)
    for chance in chances:
        mark = "  problem" if chance.move_number in problems else ""
        print(
            f"  move {chance.move_number:3}: after {chance.opponent_move.color} {chance.opponent_move.gtp():4}"
            f" lost {chance.opponent_loss:5.1f}, you played {chance.my_move.gtp():4} lost {chance.my_loss:5.1f};"
            f" best {chance.best_move or '-'}{mark}"
        )


if __name__ == "__main__":
    sys.exit(main())
