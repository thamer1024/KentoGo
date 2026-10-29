"""The version of KentoGo, shown at the bottom of the top screen.

The programs of the releases on GitHub have a file version.txt next to this module, written by
.github/workflows/release.yaml (see packaging/release_version.py). KentoGo run from the source
has no such file, and then no version is shown; to see one, write it in src/kentogo/version.txt
(the file is not in git), for example "dev".
"""

from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent / "version.txt"


def app_version(path: Path = VERSION_FILE) -> str:
    """Read the version of KentoGo, such as "1.2.0".

    Args:
        path: The file with the version.

    Returns:
        The version, or "" when there is no file or it is empty.
    """
    try:
        # utf-8-sig: a file written on Windows may start with a byte order mark.
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""
