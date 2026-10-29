"""The games in the games folder, for the list of the screen that shows games.

The list must open at once even with many games, so the files are not read as games here:
whether a game has an AI commentary is found by looking for the headers of the commentary
in the text of the file (see record.ai_comment).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kentogo.record.ai_comment import MOVE_HEADERS, REVIEW_HEADERS

# The middle line of a review header is enough (KaTrain may change the lines around it).
_AI_MARKS = tuple(header.encode("utf-8") for header in (*MOVE_HEADERS, *(h.splitlines()[1] for h in REVIEW_HEADERS)))


@dataclass(frozen=True)
class GameFile:
    """A game in the games folder.

    Attributes:
        path: The SGF file.
        modified_ns: The time of change of the file.
        has_ai: True if the file has an AI commentary (found from its text, see the module docstring).
    """

    path: Path
    modified_ns: int
    has_ai: bool

    @property
    def name(self) -> str:
        """The name of the SGF file."""
        return self.path.name


def list_games(folder: Path) -> list[GameFile]:
    """Return the games in a folder (not in its subfolders), the newest first. Unreadable files are left out."""
    games = []
    for path in folder.glob("*.sgf"):
        try:
            games.append(GameFile(path, path.stat().st_mtime_ns, _has_ai(path.read_bytes())))
        except OSError:
            continue
    return sorted(games, key=lambda game: (-game.modified_ns, game.name))


def games_with_ai(games: list[GameFile]) -> list[GameFile]:
    """Return only the games that have an AI commentary, in the same order."""
    return [game for game in games if game.has_ai]


def _has_ai(data: bytes) -> bool:
    """Return True if the text of an SGF file has a header of the AI commentary (UTF-8 files only)."""
    return any(mark in data for mark in _AI_MARKS)
