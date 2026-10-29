"""Text diagrams of the board, in the same form as the user's script.

    X = black stone, O = white stone, . = empty point
    x / o = the opponent's last move
    # = the move that was played, * = the best move

Columns are GTP letters (no "I"), and rows are numbers with the top row first.
A diagram can show the whole board or a part of it (a zoomed diagram).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.common.board import Point
from kentogo.common.types import GTP_COLUMNS, Move

MARK_PLAYED = "#"
MARK_BEST = "*"
_STONES = {"B": "X", "W": "O"}
_LAST_MOVE = {"B": "x", "W": "o"}


@dataclass(frozen=True)
class Region:
    """A rectangle of the board, with both ends included (x is the column, y the row from the bottom)."""

    left: int
    bottom: int
    right: int
    top: int

    @classmethod
    def whole(cls, size: int) -> Region:
        """Return the whole board."""
        return cls(0, 0, size - 1, size - 1)


def region_around(points: list[Point], size: int, margin: int, minimum: int) -> Region:
    """Return the smallest region that has all points with a margin, at least minimum points wide and tall.

    Args:
        points: The points to show (an empty list gives the whole board).
        size: The size of the board.
        margin: How many points to show around them.
        minimum: The smallest width and height (it is made smaller on a smaller board).

    Returns:
        The region, inside the board.
    """
    if not points:
        return Region.whole(size)
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    left, right = _span(min(xs) - margin, max(xs) + margin, size, minimum)
    bottom, top = _span(min(ys) - margin, max(ys) + margin, size, minimum)
    return Region(left, bottom, right, top)


def _span(low: int, high: int, size: int, minimum: int) -> tuple[int, int]:
    """Cut low..high to the board, then widen it to at least minimum points (away from the edges)."""
    low, high = max(low, 0), min(high, size - 1)
    missing = min(minimum, size) - (high - low + 1)
    if missing > 0:
        low = max(0, low - (missing + 1) // 2)
        high = min(size - 1, low + min(minimum, size) - 1)
        low = high - min(minimum, size) + 1
    return low, high


def render(
    stones: dict[Point, str],
    region: Region,
    last_move: Move | None = None,
    marks: dict[Point, str] | None = None,
) -> str:
    """Draw a region of the board as text.

    Args:
        stones: The stones, as a dict from point to color.
        region: The part of the board to draw.
        last_move: The opponent's last move, drawn with a small letter (or None).
        marks: Other marks (MARK_PLAYED, MARK_BEST), drawn over everything else.

    Returns:
        The diagram, with the column letters above and below and the row numbers on both sides.
    """
    columns = " ".join(GTP_COLUMNS[x] for x in range(region.left, region.right + 1))
    lines = ["   " + columns]
    for y in range(region.top, region.bottom - 1, -1):
        cells = [_cell((x, y), stones, last_move, marks or {}) for x in range(region.left, region.right + 1)]
        lines.append(f"{y + 1:>2} " + " ".join(cells) + f" {y + 1}")
    lines.append("   " + columns)
    return "\n".join(lines)


def _cell(point: Point, stones: dict[Point, str], last_move: Move | None, marks: dict[Point, str]) -> str:
    """Return the character of one point."""
    if point in marks:
        return marks[point]
    color = stones.get(point)
    if color is None:
        return "."
    if last_move is not None and last_move.coord == point:
        return _LAST_MOVE[color]
    return _STONES[color]
