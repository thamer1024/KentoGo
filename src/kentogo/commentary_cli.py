"""A command line for the AI commentary of one game, to use it before its screens are made.

Through the API (the key in the environment variable named in the settings):

    uv run python -m kentogo.commentary_cli GAME.sgf --rank 18k

In the paste mode, in two steps: write the prompt into a file, give it to any AI, save the
AI's answer into a file, and write the answer into the game:

    uv run python -m kentogo.commentary_cli GAME.sgf --rank 18k --paste --out prompt.txt
    uv run python -m kentogo.commentary_cli GAME.sgf --rank 18k --paste --answer answer.txt

The user's color is found as in the quiz, or given with --color. If the game already has an
AI commentary, the command asks before replacing it (--yes replaces it without asking).
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from kentogo.app_settings import AppSettings
from kentogo.commentary.batch import STATUS_DONE, BatchListener, GameOutcome, run_batch
from kentogo.commentary.candidates import guess_relation
from kentogo.commentary.history import CommentaryHistory, history_path
from kentogo.commentary.job import GameRequest, NotAnalyzedError, NothingToExplainError
from kentogo.commentary.paste import apply_paste, prepare_paste, remember_not_analyzed
from kentogo.commentary.prompt import RELATIONS
from kentogo.commentary.prompt_text import load_prompt_text
from kentogo.commentary.provider_base import ProviderError
from kentogo.commentary.providers import make_provider
from kentogo.common import sgf
from kentogo.mistakes.extract import ExtractSettings
from kentogo.record.game_record import read_game_record
from kentogo.record.players import detect_my_color
from kentogo.settings_file import SETTINGS_PATH, load_settings


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(prog="python -m kentogo.commentary_cli", description=__doc__.splitlines()[0])
    parser.add_argument("game", type=Path, help="the SGF file")
    parser.add_argument("--color", choices=("B", "W"), help="the user's color (found as in the quiz if not given)")
    parser.add_argument("--rank", default="", help="the user's rank at the time of the game, such as 18k or 3d")
    parser.add_argument(
        "--relation", choices=[r for r in RELATIONS if r], help="the opponent's rank (default: from komi)"
    )
    parser.add_argument("--paste", action="store_true", help="the paste mode, instead of the API")
    parser.add_argument("--out", type=Path, help="with --paste: write the prompt into this file (default: show it)")
    parser.add_argument(
        "--answer", type=Path, help="with --paste: the file with the AI's answer, to write into the game"
    )
    parser.add_argument("--yes", action="store_true", help="replace an AI commentary without asking")
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH, help="the settings file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the command. Returns the exit code (0 when the commentary was written or the prompt was made)."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")  # A Windows console may not show all characters.
    arguments = parse_arguments(argv)
    settings = load_settings(arguments.settings)
    request = make_request(arguments, settings)
    if request is None:
        return 2
    if not arguments.yes and not ask_to_replace(request.path):
        print("Nothing was changed.")
        return 1
    history = CommentaryHistory(history_path(arguments.settings))
    try:
        if arguments.paste:
            return run_paste(arguments, request, history, settings.quiz.extract)
        return run_api(arguments, request, settings, history)
    finally:
        history.close()


def make_request(arguments: argparse.Namespace, settings: AppSettings) -> GameRequest | None:
    """Make the request from the arguments, finding the color and the opponent's rank if they are not given."""
    root = sgf.load_game(arguments.game)
    color = arguments.color or detect_my_color(
        str(root.get_property("PB", "")),
        str(root.get_property("PW", "")),
        settings.quiz.extract.my_names,
        ranks=(str(root.get_property("BR", "")), str(root.get_property("WR", ""))),
        file_name=arguments.game.name,
    )
    if color is None:
        print("The user's color cannot be found: give it with --color B or --color W.", file=sys.stderr)
        return None
    relation = arguments.relation or guess_relation(sgf.komi(root), color)
    print(f"{arguments.game.name}: the user is {'black' if color == 'B' else 'white'}, rank {arguments.rank or '-'}")
    return GameRequest(arguments.game, color, arguments.rank, relation)


def ask_to_replace(path: Path) -> bool:
    """If the game has an AI commentary, ask whether to replace it. Returns True to go on."""
    if not read_game_record(sgf.load_game(path)).ai_positions():
        return True
    reply = input("This game already has an AI commentary. Replace it? [y/N] ")
    return reply.strip().lower() in ("y", "yes")


def run_api(
    arguments: argparse.Namespace, request: GameRequest, settings: AppSettings, history: CommentaryHistory
) -> int:
    """Ask the AI through its API, showing the answer as it arrives, and write it."""
    text, problems = load_prompt_text(arguments.settings)
    for problem in problems:
        print(f"prompt file {problem.path}: {problem.kind} {problem.section} {problem.detail}", file=sys.stderr)
    try:
        provider = make_provider(settings.commentary)
    except ProviderError as error:
        print(f"The AI cannot be asked: {error}", file=sys.stderr)
        return 1
    listener = BatchListener(on_text=lambda piece: print(piece, end="", flush=True))
    conditions = settings.quiz.extract
    outcome = run_batch([request], provider, text, history, listener, threading.Event(), conditions)[0]
    print()
    report_outcome(outcome, settings)
    return 0 if outcome.status == STATUS_DONE else 1


def report_outcome(outcome: GameOutcome, settings: AppSettings) -> None:
    """Show what happened to the game, the problems of the answer, and the numbers of tokens."""
    print(f"Result: {outcome.status} {outcome.error_kind} {outcome.detail}".rstrip())
    for problem in outcome.problems:
        print(f"  {'error' if problem.is_error else 'warning'}: {problem.kind} move={problem.move} {problem.field}")
    generation = outcome.generation
    if generation is not None:
        print(f"Tokens: input {generation.input_tokens:,}, output {generation.output_tokens:,}")
        if generation.truncated:
            print("The answer was cut at max_tokens: make max_tokens larger in the settings.")
    if outcome.backup is not None:
        print(f"Copy of the file before writing: {outcome.backup}")


def run_paste(
    arguments: argparse.Namespace, request: GameRequest, history: CommentaryHistory, conditions: ExtractSettings
) -> int:
    """The paste mode: make the prompt, or write the answer that the user saved into a file."""
    text, _ = load_prompt_text(arguments.settings)
    try:
        prepared = prepare_paste(request, text, conditions)
    except NotAnalyzedError:
        remember_not_analyzed(request, history)
        print("KaTrain has not analyzed this game: analyze it in KaTrain and save it first.", file=sys.stderr)
        return 1
    except NothingToExplainError:
        print("No move of this game becomes a problem of the quiz, so there is nothing to explain.", file=sys.stderr)
        return 1
    if arguments.answer is None:
        if arguments.out is None:
            print(prepared.prompt.for_paste())
        else:
            arguments.out.write_text(prepared.prompt.for_paste(), encoding="utf-8")
            print(f"The prompt was written to {arguments.out}. Give it to an AI, and save its answer into a file.")
        return 0
    try:
        answer_text = arguments.answer.read_text(encoding="utf-8-sig")  # Also reads a file with a BOM.
    except (OSError, UnicodeDecodeError) as error:
        print(f"The answer file cannot be read: {arguments.answer} ({error})", file=sys.stderr)
        return 1
    result = apply_paste(prepared, answer_text, history)
    for problem in result.answer.problems:
        print(f"  {'error' if problem.is_error else 'warning'}: {problem.kind} move={problem.move} {problem.field}")
    if result.written is None:
        print(f"Nothing was written. {result.error}".rstrip())
        return 1
    print(
        f"Written: moves {', '.join(map(str, result.written.moves))}. Copy of the file before: {result.written.backup}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
