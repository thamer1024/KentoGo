"""Find games that ended by counting, and their final positions, for the territory counting practice.

A game that one player resigned (or lost on time or by forfeit) does not end with
a finished board, so it cannot be counted. A game is used when its result (the RE
property) is a score, such as "B+3.5", or a draw. When the file has no result, the
game is used if it ends with two passes in a row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from kentogo.common import sgf
from kentogo.common.types import Move, Position, opponent

# A result with a score, such as "B+3.5" or "W+12", and the results of a draw.
SCORE_RESULT = re.compile(r"[BW]\+\d+(\.\d+)?")
DRAW_RESULTS = ("0", "DRAW", "JIGO", "D")


@dataclass(frozen=True)
class FinishedGame:
    """A game that ended by counting.

    Attributes:
        path: The SGF file.
        position: The final position (all moves of the real game played).
        result: The result written in the file (RE), or "" if there is none.
    """

    path: Path
    position: Position
    result: str


def ended_by_counting(result: str, moves: tuple[Move, ...]) -> bool:
    """Return True if a game ended with a finished board that can be counted.

    Args:
        result: The RE property, or "" if the file has none.
        moves: The moves of the real game.
    """
    text = result.strip().upper()
    if text:
        return bool(SCORE_RESULT.fullmatch(text)) or text in DRAW_RESULTS
    return len(moves) >= 2 and moves[-1].is_pass and moves[-2].is_pass


def read_finished_game(path: Path) -> FinishedGame | None:
    """Read a game, and return it if it ended by counting.

    Args:
        path: The SGF file.

    Returns:
        The game, or None if it did not end by counting (for example, a player resigned).

    Raises:
        Exception: Whatever pysgf raises for a broken file.
    """
    root = sgf.load_game(path)
    result = root.get_property("RE", "") or ""
    moves = tuple(move for node in sgf.main_line(root)[1:] if (move := sgf.node_move(node)) is not None)
    if not ended_by_counting(result, moves):
        return None
    next_color = opponent(moves[-1].color) if moves else "B"
    position = Position(
        sgf.board_size(root), sgf.komi(root), sgf.rules(root), sgf.setup_stones(root), moves, next_color
    )
    return FinishedGame(path, position, result)
