"""Keep the problems made from each SGF file, so that unchanged files are not read again.

Reading all SGF files at every start gets slow when there are many games. The
cache keeps, for each file, the problems made from it, together with what the
file looked like (its time of change and size) and the settings used to make
them. A file is read again only when it has changed, or the settings have
changed, or CACHE_VERSION has changed.

The cache can be deleted at any time: it is made again from the SGF files.

Bump CACHE_VERSION when a change of KentoGo makes different problems from the
same file (for example a change of extract.py or of the KaTrain texts).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kentogo.mistakes.extract import ExtractResult, ExtractSettings
from kentogo.quiz.problem_json import result_from_dict, result_to_dict

CACHE_VERSION = 6  # 2: games without analysis are reported. 3: candidate losses from KT.
# 4: the user's color is also found from the ranks and the file name.
# 5: the AI commentary is kept apart from the user's notes.
# (The cache key also changed with version 5: the recorded color is part of it.)
# 6: problems in decided positions and with the same best move come last (see mistakes.selection).

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    modified_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    key TEXT NOT NULL,
    result TEXT NOT NULL,
    error TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class FileStamp:
    """What a file looked like when it was read.

    Attributes:
        modified_ns: The time of the last change, in nanoseconds.
        size: The size in bytes.
    """

    modified_ns: int
    size: int

    @classmethod
    def of(cls, path: Path) -> FileStamp:
        """Return the stamp of a file now.

        Raises:
            OSError: If the file cannot be read.
        """
        stat = path.stat()
        return cls(stat.st_mtime_ns, stat.st_size)


@dataclass(frozen=True)
class CachedFile:
    """What the cache knows about one file.

    Attributes:
        result: The problems made from the file (empty if it could not be read).
        error: Why the file could not be read, or "" if it was read.
    """

    result: ExtractResult
    error: str = ""


def settings_key(settings: ExtractSettings) -> str:
    """Return a text that changes when the version or anything in the settings changes."""
    return json.dumps({"version": CACHE_VERSION, **settings.to_dict()}, sort_keys=True, ensure_ascii=False)


class ProblemCache:
    """The problems of each SGF file, in an SQLite file.

    Changes are kept in memory until commit() is called, so that writing many
    files at the first start is fast.

    Attributes:
        path: Path of the cache file.
    """

    def __init__(self, path: str | Path):
        """Open the cache, and make its table if it does not exist.

        Args:
            path: Path of the cache file. ":memory:" makes a cache that is not saved (for tests).

        Raises:
            sqlite3.Error: If the file cannot be opened or is not a database.
        """
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        try:
            with self._connection:
                self._connection.execute(_CREATE_TABLE)
        except BaseException:
            self._connection.close()
            raise

    def get(self, path: Path, stamp: FileStamp, key: str) -> CachedFile | None:
        """Return what was kept for a file, or None if the file or the settings have changed since.

        Args:
            path: Path of the SGF file.
            stamp: The stamp of the file now.
            key: The settings key now (see settings_key).
        """
        row = self._connection.execute(
            "SELECT modified_ns, size, key, result, error FROM files WHERE path = ?", (str(path),)
        ).fetchone()
        if row is None or (row[0], row[1], row[2]) != (stamp.modified_ns, stamp.size, key):
            return None
        try:
            return CachedFile(result_from_dict(json.loads(row[3])), row[4])
        except (KeyError, TypeError, ValueError):
            return None  # Broken data: the file is read again.

    def put(self, path: Path, stamp: FileStamp, key: str, cached: CachedFile) -> None:
        """Keep what was made from a file (written to the cache file at commit())."""
        text = json.dumps(result_to_dict(cached.result), ensure_ascii=False)
        self._connection.execute(
            "INSERT OR REPLACE INTO files (path, modified_ns, size, key, result, error) VALUES (?, ?, ?, ?, ?, ?)",
            (str(path), stamp.modified_ns, stamp.size, key, text, cached.error),
        )

    def forget_others(self, folder: Path, paths: list[Path]) -> None:
        """Remove the files of a folder that are no longer there (written at commit()).

        Args:
            folder: The games folder.
            paths: The SGF files that are in the folder now.
        """
        keep = {str(path) for path in paths}
        rows = self._connection.execute("SELECT path FROM files").fetchall()
        gone = [(row[0],) for row in rows if Path(row[0]).parent == folder and row[0] not in keep]
        self._connection.executemany("DELETE FROM files WHERE path = ?", gone)

    def commit(self) -> None:
        """Write the changes to the cache file."""
        self._connection.commit()

    def close(self) -> None:
        """Close the cache. Changes that were not committed are lost (they are only a cache)."""
        self._connection.close()
