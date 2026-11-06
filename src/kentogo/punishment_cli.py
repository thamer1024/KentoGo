"""A command line that lists the moments when the opponent made a big mistake and the user did not punish it.

It is for checking the "punishment problems" before they are asked in the quiz:

    uv run python -m kentogo.punishment_cli                     # the games folder of the settings
    uv run python -m kentogo.punishment_cli GAME.sgf FOLDER ...
    uv run python -m kentogo.punishment_cli --opponent-loss 15 --my-loss 5

A moment counts when the opponent's move lost at least --opponent-loss points and the user's next
move lost at least --my-loss points (by default the settings punish_opponent_loss and punish_my_loss). Each moment is one of two kinds:
"punish" (the opponent's mistake made a new chance) or "shared" (both missed the same point).
When both keep missing the same point, only the first moment counts. "decided" marks moments in
decided positions (--skip-decided leaves them out), and "problem" the ones that are already
problems of the quiz (see mistakes.extract).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kentogo.common.sgf import load_game
from kentogo.mistakes.extract import PUNISH, SHARED, PunishmentChance, extract_problems, punishment_chances
from kentogo.settings_file import SETTINGS_PATH, load_settings


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(prog="python -m kentogo.punishment_cli", description=__doc__.splitlines()[0])
    parser.add_argument("paths", type=Path, nargs="*", help="SGF files or folders (default: the games folder)")
    parser.add_argument("--opponent-loss", type=float, help="the opponent's smallest loss (default: the settings)")
    parser.add_argument("--my-loss", type=float, help="the smallest loss of your move (default: the settings)")
    parser.add_argument("--skip-decided", action="store_true", help="leave out moments in decided positions")
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
    conditions = settings.quiz.extract
    opponent_loss = conditions.punish_opponent_loss if arguments.opponent_loss is None else arguments.opponent_loss
    my_loss = conditions.punish_my_loss if arguments.my_loss is None else arguments.my_loss
    print(f"Opponent's loss {opponent_loss:g}+ points, your loss {my_loss:g}+ points")
    found: list[PunishmentChance] = []
    for path in games:
        try:
            root = load_game(path)
        except Exception as error:  # A broken file must not stop the others.
            print(f"{path.name}: cannot be read: {error}")
            continue
        chances = punishment_chances(root, str(path), conditions, opponent_loss, my_loss)
        chances = [chance for chance in chances if not (arguments.skip_decided and chance.decided)]
        problems = {
            problem.move_number for problem in extract_problems(root, str(path), settings.quiz.extract).problems
        }
        found += chances
        show_game(path, chances, problems)
    print(summary(found, len(games)))
    return 0


def summary(chances: list[PunishmentChance], games: int) -> str:
    """Return the last line: how many moments of each kind, and how many in decided positions."""
    kinds = {kind: sum(1 for chance in chances if chance.kind == kind) for kind in (PUNISH, SHARED)}
    decided = sum(1 for chance in chances if chance.decided)
    return (
        f"Done: {len(chances)} moments in {games} games"
        f" (punish {kinds[PUNISH]}, shared {kinds[SHARED]}; decided {decided})."
    )


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
        marks = ("  decided" if chance.decided else "") + ("  problem" if chance.move_number in problems else "")
        print(
            f"  move {chance.move_number:3} {chance.kind:6}: after {chance.opponent_move.color}"
            f" {chance.opponent_move.gtp():4} lost {chance.opponent_loss:5.1f} (best {chance.opponent_best or '-':4}),"
            f" you played {chance.my_move.gtp():4} lost {chance.my_loss:5.1f}; best {chance.best_move or '-'}{marks}"
        )


if __name__ == "__main__":
    sys.exit(main())
