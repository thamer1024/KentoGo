"""The order of the game files in the lists of the screens: the most recently changed first."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def newest_first(paths: Iterable[Path]) -> list[Path]:
    """Return the files with the most recently changed first, and files changed at the same time by name.

    A file whose time cannot be read (it was removed, for example) comes last.
    """
    return sorted(paths, key=_newest_first_key)


def _newest_first_key(path: Path) -> tuple[bool, int, str]:
    """Return the sort key of newest_first: readable files first, the newest first, then by name."""
    try:
        return (False, -path.stat().st_mtime_ns, path.name)
    except OSError:
        return (True, 0, path.name)
