"""What the board shows: stones, numbers of a sequence, and marks.

This module decides what to draw, without Kivy, so that it can be tested.
BoardWidget only draws a BoardView.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from kentogo.common.board import Board, IllegalMoveError
from kentogo.common.types import Move, Position

Point = tuple[int, int]

# Kinds of marks. The screen draws each kind in its own color.
MARK_ANSWER = "answer"
MARK_ACTUAL = "actual"
MARK_BEST = "best"
MARK_COMPARE = "compare"  # The comparison model's best move.

# The shape of each kind of mark (see mark_outline).
SHAPE_CIRCLE = "circle"
SHAPE_TRIANGLE = "triangle"
SHAPE_SQUARE = "square"
SHAPE_STAR = "star"
MARK_SHAPES = {
    MARK_ANSWER: SHAPE_CIRCLE,
    MARK_ACTUAL: SHAPE_TRIANGLE,
    MARK_BEST: SHAPE_SQUARE,
    MARK_COMPARE: SHAPE_STAR,
}


@dataclass(frozen=True)
class BoardView:
    """Everything that the board shows at one time.

    Attributes:
        size: Number of lines of the board.
        stones: The stones on the board, as {point: "B" or "W"}.
        numbers: Numbers to write on stones of a sequence, as {point: number}.
        last_move: The point of the last move of the position, or None.
        marks: Marks to draw on points, as {point: kinds}, such as (MARK_ANSWER,). When a point has
            several kinds, they are drawn as rings inside each other, the first one outside.
        dead: Stones marked dead (territory counting practice). They are drawn faded, with a cross.
        territory: The owner of each point of territory, as {point: "B" or "W"} (territory counting
            practice). A small square of the owner's color is drawn on each.
        ownership: KataGo's owner of each point, from black's side (1: black, -1: white), to show the
            territory as KaTrain does: a square of the owner's color, larger the surer it is, on
            empty points and on stones that the other player is sure to get (dead stones).
    """

    size: int
    stones: dict[Point, str]
    numbers: dict[Point, int] = field(default_factory=dict)
    last_move: Point | None = None
    marks: dict[Point, tuple[str, ...]] = field(default_factory=dict)
    dead: frozenset[Point] = frozenset()
    territory: dict[Point, str] = field(default_factory=dict)
    ownership: dict[Point, float] = field(default_factory=dict)


def collect_marks(moves: list[tuple[Move | None, str]]) -> dict[Point, tuple[str, ...]]:
    """Put marks for moves together by point, so that moves on the same point keep all their marks.

    Args:
        moves: (move, kind) in the order to draw them, from the outside ring. A None move or a
            pass gets no mark, and the same kind is not repeated on a point.

    Returns:
        The marks, as {point: kinds}.
    """
    marks: dict[Point, tuple[str, ...]] = {}
    for move, kind in moves:
        if move is not None and move.coord is not None and kind not in marks.get(move.coord, ()):
            marks[move.coord] = (*marks.get(move.coord, ()), kind)
    return marks


def make_board_view(
    position: Position, sequence: tuple[Move, ...] = (), marks: dict[Point, tuple[str, ...]] | None = None
) -> BoardView:
    """Make the view of a position, with a sequence played on top of it.

    Args:
        position: The position.
        sequence: Moves to play after the position. They get numbers 1, 2, 3, ...
            If a move cannot be played, it and the moves after it are not shown.
        marks: Marks to draw, as {point: kinds} (see collect_marks).

    Returns:
        The view. A number is shown only while its stone is still on the board,
        and only the newest number is shown on a point.
    """
    board = Board.from_position(position)
    numbers: dict[Point, int] = {}
    for number, move in enumerate(sequence, start=1):
        try:
            board.play(move)
        except IllegalMoveError:
            break
        if move.coord is not None:
            numbers[move.coord] = number
    stones = board.stones()
    numbers = {point: number for point, number in numbers.items() if point in stones}
    last_move = position.moves[-1].coord if position.moves else None
    return BoardView(position.size, stones, numbers, last_move, dict(marks or {}))


def mark_outline(kind: str, center: tuple[float, float], radius: float) -> list[float] | None:
    """Return the corners of the outline of a mark, or None for a circle.

    Each kind has its own shape as well as its own color, so that users who cannot tell
    the colors apart can tell the marks apart by their shapes.

    Args:
        kind: The kind of the mark, such as MARK_ANSWER.
        center: The center of the point on the screen.
        radius: The size of the mark: the radius of its circle, or of the circle around its corners.

    Returns:
        The corners as [x1, y1, x2, y2, ...] (the outline closes by itself), or None for a circle.
    """
    shape = MARK_SHAPES.get(kind, SHAPE_CIRCLE)
    if shape == SHAPE_TRIANGLE:
        corners = [(radius, 90 + 120 * i) for i in range(3)]  # Pointing up.
    elif shape == SHAPE_SQUARE:
        corners = [(radius, 45 + 90 * i) for i in range(4)]
    elif shape == SHAPE_STAR:
        # Five points, with the inner corners at less than half of the radius.
        corners = [(radius if i % 2 == 0 else radius * 0.45, 90 + 36 * i) for i in range(10)]
    else:
        return None
    x, y = center
    points: list[float] = []
    for length, degrees in corners:
        angle = math.radians(degrees)
        points += [x + length * math.cos(angle), y + length * math.sin(angle)]
    return points
