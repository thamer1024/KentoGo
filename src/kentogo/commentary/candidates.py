"""The list of games for the AI commentary: which games to show, and the first values of the inputs.

A game in the games folder is shown when:

- it is pending (KaTrain had not analyzed it when it was shown before), or
- it was changed after `since_ns` (the time of the last run, or the date chosen at the first run),

and it is not excluded, and it was not changed since KentoGo wrote its commentary.

For each game, the first values of the inputs are found: the user's color (given before,
or found as in the quiz), the user's rank (given before, or from the rank in the SGF file,
such as in games from Fox Weiqi, or a default), and the rank of the opponent (given before,
or guessed from the komi). The screen shows them, and the user can change them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from kentogo.commentary.history import STATE_DONE, STATE_EXCLUDED, STATE_PENDING, CommentaryHistory, GameEntry
from kentogo.commentary.material import has_katrain_evaluation
from kentogo.commentary.prompt import RELATION_HIGHER, RELATION_LOWER, RELATION_SAME
from kentogo.commentary.targets import normalize_rank
from kentogo.common import sgf
from kentogo.record.game_record import BoardState, GameRecord, read_game_record
from kentogo.record.players import detect_my_color

# The komi of an even game is at least this; with at most NO_KOMI, the weaker player takes black.
EVEN_KOMI = 5.0
NO_KOMI = 1.0


@dataclass(frozen=True)
class GameCandidate:
    """A game in the list, with the first values of the inputs.

    Attributes:
        path: The SGF file.
        modified_ns: The time of change of the file.
        pending: True if the game was pending (shown before without KaTrain's analysis).
        my_color: "B", "W", or "" if it could not be found (the user must choose it).
        my_rank: The user's rank ("" if not known).
        relation: The rank of the opponent compared with the user (see prompt.RELATIONS).
        analyzed: True if KaTrain has analyzed the game.
        has_ai: True if the game already has an AI commentary.
        black_name: The PB property.
        white_name: The PW property.
        result: The RE property.
        final_state: The board at the end of the game (to show which game it is).
        size: The size of the board.
        error: Why the file could not be read ("" if it was read; the other values are then empty).
    """

    path: Path
    modified_ns: int
    pending: bool = False
    my_color: str = ""
    my_rank: str = ""
    relation: str = ""
    analyzed: bool = False
    has_ai: bool = False
    black_name: str = ""
    white_name: str = ""
    result: str = ""
    final_state: BoardState | None = None
    size: int = 19
    error: str = ""

    @property
    def name(self) -> str:
        """The name of the SGF file."""
        return self.path.name


def list_candidates(
    folder: Path,
    history: CommentaryHistory,
    since_ns: int,
    my_names: Iterable[str] = (),
    default_rank: str = "",
) -> list[GameCandidate]:
    """Make the list of games to show, the oldest first.

    Args:
        folder: The games folder (its subfolders are not read).
        history: What KentoGo remembers about the games.
        since_ns: Games changed after this time are shown (see the module docstring).
        my_names: The user's names (the quiz setting), to find the user's color.
        default_rank: The rank used when it is not known otherwise.

    Returns:
        The games, in the order of their time of change.
    """
    entries = history.all_entries()
    games = []
    for path in sorted(folder.glob("*.sgf")):
        try:
            modified_ns = path.stat().st_mtime_ns
        except OSError:
            continue
        entry = entries.get(path.name, GameEntry(path.name))
        if is_shown(entry, modified_ns, since_ns):
            games.append(_candidate(path, modified_ns, entry, tuple(my_names), default_rank))
    return sorted(games, key=lambda game: (game.modified_ns, game.name))


def candidate_for(
    path: Path, history: CommentaryHistory | None, my_names: Iterable[str] = (), default_rank: str = ""
) -> GameCandidate:
    """Read one game chosen by the user, with the first values of the inputs (as in the list).

    Args:
        path: The SGF file.
        history: What KentoGo remembers about the games, or None if it cannot be used.
        my_names: The user's names (the quiz setting), to find the user's color.
        default_rank: The rank used when it is not known otherwise.

    Returns:
        The game. If the file cannot be read, the candidate has the error.
    """
    entry = (history.entry(path.name) if history is not None else None) or GameEntry(path.name)
    try:
        modified_ns = path.stat().st_mtime_ns
    except OSError as error:
        return GameCandidate(path, 0, error=str(error))
    return _candidate(path, modified_ns, entry, tuple(my_names), default_rank)


def is_shown(entry: GameEntry, modified_ns: int, since_ns: int) -> bool:
    """Return True if a game is shown in the list (see the module docstring)."""
    if entry.state == STATE_EXCLUDED:
        return False
    if entry.state == STATE_DONE and entry.done_modified_ns == modified_ns:
        return False
    return entry.state == STATE_PENDING or modified_ns > since_ns


def guess_relation(komi: float, my_color: str) -> str:
    """Guess the rank of the opponent from the komi, as the user's script does.

    An even game (komi of EVEN_KOMI or more) is against the same rank. Without komi, the
    weaker player takes black. Otherwise, or without the user's color, nothing is guessed.
    """
    if komi >= EVEN_KOMI:
        return RELATION_SAME
    if komi <= NO_KOMI and my_color in ("B", "W"):
        return RELATION_HIGHER if my_color == "B" else RELATION_LOWER
    return ""


def _candidate(
    path: Path, modified_ns: int, entry: GameEntry, my_names: tuple[str, ...], default_rank: str
) -> GameCandidate:
    """Read one game and make its line of the list."""
    pending = entry.state == STATE_PENDING
    try:
        root = sgf.load_game(path)
        record = read_game_record(root)
    except Exception as error:  # A broken file is shown with its error, and does not stop the list.
        return GameCandidate(path, modified_ns, pending, error=str(error) or type(error).__name__)
    color = entry.my_color or _detect_color(root, path, my_names)
    return GameCandidate(
        path=path,
        modified_ns=modified_ns,
        pending=pending,
        my_color=color,
        my_rank=entry.my_rank or _rank_in_game(root, color) or normalize_rank(default_rank),
        relation=entry.relation or guess_relation(record.komi, color),
        analyzed=_is_analyzed(record, color),
        has_ai=bool(record.ai_positions()),
        black_name=record.black_name,
        white_name=record.white_name,
        result=record.result,
        final_state=record.final_state(),
        size=record.size,
    )


def _detect_color(root, path: Path, my_names: tuple[str, ...]) -> str:
    """Find the user's color in the same way as the quiz ("" if it cannot be found)."""
    color = detect_my_color(
        str(root.get_property("PB", "")),
        str(root.get_property("PW", "")),
        my_names,
        ranks=(str(root.get_property("BR", "")), str(root.get_property("WR", ""))),
        file_name=path.name,
    )
    return color or ""


def _rank_in_game(root, color: str) -> str:
    """Return the user's rank written in the game (BR or WR), if it is a rank KentoGo knows."""
    return normalize_rank(str(root.get_property(f"{color}R", ""))) if color in ("B", "W") else ""


def _is_analyzed(record: GameRecord, color: str) -> bool:
    """Return True if KaTrain has evaluated the user's moves (any player's moves, if the color is not known)."""
    colors = [color] if color in ("B", "W") else ["B", "W"]
    return any(has_katrain_evaluation(record, each) for each in colors)
