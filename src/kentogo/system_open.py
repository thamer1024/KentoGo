"""Open a file with the app that the computer uses for it (such as a text editor for a .txt file)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_command(path: Path, platform: str) -> list[str] | None:
    """Return the command that opens a file on a platform, or None on Windows (os.startfile is used there).

    Args:
        path: The file.
        platform: The value of sys.platform, such as "darwin", "win32" or "linux".
    """
    if platform.startswith("win"):
        return None
    if platform == "darwin":
        return ["open", "-t", str(path)]  # -t: the default text editor.
    return ["xdg-open", str(path)]


def open_with_system(path: Path) -> None:
    """Open a file with the app that the computer uses for it, without waiting for the app.

    Raises:
        OSError: If the file cannot be opened.
    """
    command = open_command(path, sys.platform)
    if command is None:
        os.startfile(path)  # type: ignore[attr-defined]  # Only on Windows.
    else:
        subprocess.Popen(command)
