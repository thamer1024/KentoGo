"""The start of the KentoGo program made with PyInstaller (KentoGo.exe on Windows, KentoGo.app on macOS).

See packaging/windows/kentogo.spec and packaging/macos/kentogo.spec. Before KentoGo starts:

- A program without a console has no sys.stdout and sys.stderr (they are None), so the messages
  of Kivy and KentoGo could not be written. They are written to ~/.kentogo/kentogo.log instead
  (made again at each start), which helps to find out what went wrong.
- An app started from the Finder gets only the PATH of the system, so a KataGo installed with
  Homebrew (KaTrain's "katago" setting) would not be found. Homebrew's folders are added.
"""

import os
import sys
from pathlib import Path

LOG_FILE = Path("~/.kentogo/kentogo.log")
# Where Homebrew puts programs (Apple silicon, then Intel).
HOMEBREW_FOLDERS = ("/opt/homebrew/bin", "/usr/local/bin")


def log_to_file() -> None:
    """Send the messages to LOG_FILE when there is no console."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    path = LOG_FILE.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    log = open(path, "w", encoding="utf-8", buffering=1)  # Kept open while the program runs.
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def add_homebrew_to_path() -> None:
    """On macOS, add Homebrew's folders to the end of the PATH, if they are not in it."""
    if sys.platform != "darwin":
        return
    folders = os.environ.get("PATH", "").split(os.pathsep)
    missing = [folder for folder in HOMEBREW_FOLDERS if folder not in folders and Path(folder).is_dir()]
    os.environ["PATH"] = os.pathsep.join([*filter(None, folders), *missing])


log_to_file()
add_homebrew_to_path()

from kentogo.app import main  # noqa: E402  (the messages must have a place before anything is imported)

if __name__ == "__main__":
    main()
