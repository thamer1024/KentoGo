"""What KentoGo remembers about the games given to an AI, kept in an SQLite database (Python's sqlite3).

For each game (known by the name of its SGF file, as in the territory counting practice):

- The inputs that the user gave in the list of games: the user's color, the user's rank,
  and the rank of the opponent compared with the user. The color is also used by the quiz
  to find the user's color, before any other way (see record.players.detect_my_color).
- The state of the game:
  - STATE_PENDING: it was in the list, but KaTrain had not analyzed it yet. It is shown
    again every time, until KaTrain has analyzed it and it gets a commentary.
  - STATE_DONE: KentoGo wrote a commentary. The time of change of the file after that
    is kept, so a later change (for example, analyzed again in KaTrain) shows it again.
  - STATE_EXCLUDED: the user chose not to show it any more. This can be undone.
  A game that is not in the database has no state.

It also keeps the time from which changed games are shown in the list (the time of the
last run, or the date that the user chose at the first run), and the last rank that the
user gave (the first value of the rank for a game without one).

Using the database must not stop KentoGo: the caller decides what to do when it cannot
be opened (the quiz simply works without the recorded colors).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

FILE_NAME = "commentary_history.sqlite3"

STATE_PENDING = "pending"
STATE_DONE = "done"
STATE_EXCLUDED = "excluded"
STATES = (STATE_PENDING, STATE_DONE, STATE_EXCLUDED)

_SINCE_KEY = "since_ns"
_LAST_RANK_KEY = "last_rank"

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS games (
    name TEXT PRIMARY KEY,
    my_color TEXT NOT NULL DEFAULT '',
    my_rank TEXT NOT NULL DEFAULT '',
    relation TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    done_modified_ns INTEGER
);
CREATE TABLE IF NOT EXISTS stored_values (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass(frozen=True)
class GameEntry:
    """What is remembered about one game.

    Attributes:
        name: The name of the SGF file.
        my_color: "B" or "W", or "" if the user has not given it.
        my_rank: The user's rank at the time of the game, such as "18k" ("" if not given).
        relation: The rank of the opponent compared with the user (a key chosen by the screen, "" if not given).
        state: One of STATES, or "" if the game has no state.
        done_modified_ns: The time of change of the file after the commentary was written (STATE_DONE only).
    """

    name: str
    my_color: str = ""
    my_rank: str = ""
    relation: str = ""
    state: str = ""
    done_modified_ns: int | None = None


class CommentaryHistory:
    """The inputs and the states of the games given to an AI.

    Every change is written to the file at once.

    Attributes:
        path: The database file.
    """

    def __init__(self, path: Path | str):
        """Open (or make) the database.

        Args:
            path: The database file. ":memory:" makes a database that is not saved (for tests).

        Raises:
            sqlite3.Error: If the database cannot be opened.
        """
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        try:
            self._connection.executescript(_CREATE_TABLES)
            self._connection.commit()
        except BaseException:
            self._connection.close()
            raise

    def entry(self, name: str) -> GameEntry | None:
        """Return what is remembered about a game, or None if nothing is."""
        row = self._connection.execute(
            "SELECT name, my_color, my_rank, relation, state, done_modified_ns FROM games WHERE name = ?", (name,)
        ).fetchone()
        return GameEntry(*row) if row else None

    def all_entries(self) -> dict[str, GameEntry]:
        """Return what is remembered about all games, by the name of the SGF file."""
        rows = self._connection.execute(
            "SELECT name, my_color, my_rank, relation, state, done_modified_ns FROM games"
        ).fetchall()
        return {row[0]: GameEntry(*row) for row in rows}

    def recorded_colors(self) -> dict[str, str]:
        """Return the user's color that the user gave for each game (games without it are left out)."""
        rows = self._connection.execute("SELECT name, my_color FROM games WHERE my_color != ''").fetchall()
        return dict(rows)

    def save_inputs(self, name: str, my_color: str, my_rank: str, relation: str) -> None:
        """Remember what the user gave for a game. The state of the game is kept.

        A rank that is not "" is also kept as the last rank (see last_rank).

        Raises:
            ValueError: If my_color is not "B", "W" or "".
        """
        if my_color not in ("B", "W", ""):
            raise ValueError(f"the color must be B, W or empty: {my_color!r}")
        self._ensure(name)
        self._write(
            "UPDATE games SET my_color = ?, my_rank = ?, relation = ? WHERE name = ?",
            (my_color, my_rank, relation, name),
        )
        if my_rank:
            self._set_value(_LAST_RANK_KEY, my_rank)

    def mark_pending(self, name: str) -> None:
        """Remember that KaTrain had not analyzed a game, so that it is shown again."""
        self._set_state(name, STATE_PENDING, None)

    def mark_done(self, name: str, modified_ns: int) -> None:
        """Remember that a commentary was written, and the time of change of the file after that."""
        self._set_state(name, STATE_DONE, modified_ns)

    def exclude(self, name: str) -> None:
        """Do not show a game any more (until include is called)."""
        self._set_state(name, STATE_EXCLUDED, None)

    def include(self, name: str) -> None:
        """Undo exclude: the game has no state again, and is shown when it is changed after since_ns."""
        self._set_state(name, "", None)

    def since_ns(self) -> int | None:
        """Return the time (in nanoseconds since the epoch) from which changed games are shown, or None at first."""
        value = self._value(_SINCE_KEY)
        return int(value) if value is not None else None

    def set_since_ns(self, since_ns: int) -> None:
        """Set the time from which changed games are shown (the time of a run, or the date chosen at first)."""
        self._set_value(_SINCE_KEY, str(since_ns))

    def last_rank(self) -> str:
        """Return the last rank that the user gave for a game ("" if none was given yet)."""
        return self._value(_LAST_RANK_KEY) or ""

    def close(self) -> None:
        """Close the database."""
        self._connection.close()

    def _value(self, key: str) -> str | None:
        """Return a stored value, or None if it was never set."""
        row = self._connection.execute("SELECT value FROM stored_values WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_value(self, key: str, value: str) -> None:
        """Set a stored value (written to the file at once)."""
        self._write("INSERT OR REPLACE INTO stored_values (key, value) VALUES (?, ?)", (key, value))

    def _set_state(self, name: str, state: str, done_modified_ns: int | None) -> None:
        """Set the state of a game (the inputs are kept)."""
        self._ensure(name)
        self._write("UPDATE games SET state = ?, done_modified_ns = ? WHERE name = ?", (state, done_modified_ns, name))

    def _ensure(self, name: str) -> None:
        """Add a row for a game if there is none (not written until _write commits)."""
        self._connection.execute("INSERT OR IGNORE INTO games (name) VALUES (?)", (name,))

    def _write(self, sql: str, parameters: tuple) -> None:
        """Run one change and write it to the file at once."""
        with self._connection:
            self._connection.execute(sql, parameters)


def history_path(settings_path: Path) -> Path:
    """Return the path of the database: in the folder of the settings file."""
    return settings_path.expanduser().parent / FILE_NAME
