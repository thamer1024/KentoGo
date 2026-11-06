"""Save an analyzed game: copy the original file to the backup folder first, then write the new one.

The original is copied byte for byte (its own text encoding is kept) and the copy is checked
before the game file is changed. The new file is written next to it under another name and then
put in its place, so a stop in the middle never leaves a half-written game. As KaTrain does,
the new file is written in UTF-8 (the root's CA property says so).
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_FOLDER_NAME = "backup"  # In the games folder, when the settings name no backup folder.


def backup_folder(games_folder: Path, setting: str) -> Path:
    """Return the backup folder: the one in the settings, or "backup" in the games folder."""
    return Path(setting).expanduser() if setting else games_folder / BACKUP_FOLDER_NAME


def back_up(path: Path, folder: Path, now: datetime) -> Path:
    """Copy a game file into the backup folder with the time in its name, and check the copy.

    Args:
        path: The game file.
        folder: The backup folder (made when it does not exist).
        now: The time written in the name of the copy.

    Returns:
        The path of the copy.

    Raises:
        OSError: If the copy cannot be made or is not the same as the original.
    """
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"{path.stem} {now:%Y-%m-%d %H%M%S}{path.suffix}"
    shutil.copy2(path, copy)
    if copy.read_bytes() != path.read_bytes():
        raise OSError(f"the backup {copy} is not the same as {path}")
    return copy


def write_game(path: Path, text: str) -> None:
    """Write the new text of a game file in UTF-8, through a file next to it, then put it in its place."""
    temporary = path.with_name(path.name + ".kentogo-tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
