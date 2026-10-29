"""The start of KentoGo.exe, the Windows program made with PyInstaller (see kentogo.spec).

A program without a console has no sys.stdout and sys.stderr (they are None), so the messages
of Kivy and KentoGo could not be written. They are written to ~/.kentogo/kentogo.log instead
(made again at each start), which helps to find out what went wrong.
"""

import sys
from pathlib import Path

LOG_FILE = Path("~/.kentogo/kentogo.log")


def log_to_file() -> None:
    """Send the messages to LOG_FILE when there is no console."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    path = LOG_FILE.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    log = open(path, "w", encoding="utf-8", buffering=1)  # Kept open while the program runs.
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


log_to_file()

from kentogo.app import main  # noqa: E402  (the messages must have a place before anything is imported)

if __name__ == "__main__":
    main()
