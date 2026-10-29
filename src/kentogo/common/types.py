"""Basic data for moves and positions.

A point on the board is (x, y). x is the column from the left, and y is the
row from the bottom, both starting at 0. This is the same as in pysgf and
in GTP coordinates ("A1" is the lower left corner).
"""

from __future__ import annotations

from dataclasses import dataclass

# GTP column letters. "I" is not used. Large boards use two letters, as in pysgf.
GTP_COLUMNS = list("ABCDEFGHJKLMNOPQRSTUVWXYZ") + [a + b for a in "ABCDEFGH" for b in "ABCDEFGHJKLMNOPQRSTUVWXYZ"]

# SGF coordinate letters.
SGF_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def opponent(color: str) -> str:
    """Return the other color ("B" for "W", and "W" for "B")."""
    return "W" if color == "B" else "B"


def moves_from_gtp(points: tuple[str, ...] | list[str], first_color: str) -> tuple[Move, ...]:
    """Turn a sequence of GTP points into moves, with the colors taking turns.

    Args:
        points: Points such as ("Q4", "D16", "pass").
        first_color: Color of the first move, "B" or "W".

    Returns:
        The moves.
    """
    colors = (first_color, opponent(first_color))
    return tuple(Move.from_gtp(point, colors[i % 2]) for i, point in enumerate(points))


@dataclass(frozen=True)
class Move:
    """One move (or a stone placed before the game, such as a handicap stone).

    Attributes:
        color: "B" or "W".
        coord: The point (x, y), or None for a pass.
    """

    color: str
    coord: tuple[int, int] | None

    @property
    def is_pass(self) -> bool:
        """True if this move is a pass."""
        return self.coord is None

    def gtp(self) -> str:
        """Return the point in GTP coordinates, such as "Q16" or "pass"."""
        if self.coord is None:
            return "pass"
        x, y = self.coord
        return f"{GTP_COLUMNS[x]}{y + 1}"

    @classmethod
    def from_gtp(cls, text: str, color: str) -> Move:
        """Make a move from GTP coordinates.

        Args:
            text: A point such as "Q16", or "pass". Lower case letters are also accepted.
            color: "B" or "W".

        Returns:
            The move.

        Raises:
            ValueError: If the text is not a GTP point.
        """
        text = text.strip().upper()
        if text == "PASS":
            return cls(color, None)
        column = text.rstrip("0123456789")
        row = text[len(column) :]
        if column not in GTP_COLUMNS or not row:
            raise ValueError(f"not a GTP point: {text!r}")
        return cls(color, (GTP_COLUMNS.index(column), int(row) - 1))

    def sgf(self, size: int) -> str:
        """Return the point in SGF coordinates, such as "pd". A pass is "".

        Args:
            size: Size of the board. SGF counts rows from the top, so it is needed.
        """
        if self.coord is None:
            return ""
        x, y = self.coord
        return SGF_LETTERS[x] + SGF_LETTERS[size - 1 - y]

    @classmethod
    def from_sgf(cls, text: str, color: str, size: int) -> Move:
        """Make a move from SGF coordinates.

        Args:
            text: A point such as "pd". "" is a pass, and so is "tt" on boards up to 19x19.
            color: "B" or "W".
            size: Size of the board.

        Returns:
            The move.

        Raises:
            ValueError: If the text is not an SGF point.
        """
        if text == "" or (text == "tt" and size <= 19):
            return cls(color, None)
        if len(text) != 2 or text[0] not in SGF_LETTERS or text[1] not in SGF_LETTERS:
            raise ValueError(f"not an SGF point: {text!r}")
        return cls(color, (SGF_LETTERS.index(text[0]), size - 1 - SGF_LETTERS.index(text[1])))


@dataclass(frozen=True)
class Position:
    """A position on the board, given as stones placed first and the moves after them.

    Attributes:
        size: Size of the board (19 for a 19x19 board).
        komi: Komi of the game.
        rules: The rules as written in the RU property of the SGF file (see common.rules).
        setup: Stones placed before the first move, such as handicap stones.
        moves: The moves played from the start, in order.
        next_color: Color of the player to move next.
    """

    size: int
    komi: float
    rules: str
    setup: tuple[Move, ...]
    moves: tuple[Move, ...]
    next_color: str
