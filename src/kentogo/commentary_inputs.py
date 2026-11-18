"""What the user gave for the AI commentary and the practices use: the color and the rank in each game.

Only this module reads them from the history of the AI commentary for the practices.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from kentogo.commentary.history import CommentaryHistory, history_path


def read_recorded_colors(settings_path: Path) -> dict[str, str]:
    """Read the user's colors given in the list of games for the AI commentary.

    Args:
        settings_path: Path of the settings file (the database is next to it).

    Returns:
        The color by the name of the SGF file, or an empty dict if the database
        cannot be read (the reason is printed; the colors are then found in other ways).
    """
    path = history_path(settings_path)
    if not path.exists():
        return {}
    try:
        history = CommentaryHistory(path)
        try:
            return history.recorded_colors()
        finally:
            history.close()
    except (sqlite3.Error, OSError) as error:
        print(f"cannot read the commentary history {path}: {error}", file=sys.stderr)
        return {}


def given_rank(settings_path: Path, name: str) -> str:
    """Return the user's rank given for the AI commentary of a game, else the last one given ("" if none).

    Args:
        settings_path: The settings file (the history of the AI commentary is next to it).
        name: The file name of the game.
    """
    path = history_path(settings_path)
    if not path.is_file():  # The AI commentary was never used (the history is not made here).
        return ""
    try:
        history = CommentaryHistory(path)
    except Exception:  # A history that cannot be opened: no rank is known.
        return ""
    try:
        entry = history.entry(name)
        return (entry.my_rank if entry is not None else "") or history.last_rank()
    finally:
        history.close()
