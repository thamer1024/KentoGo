"""The chase of a group that is about to be captured, such as a ladder (no Kivy, no KataGo).

KataGo's areas settle long before such a group leaves the board. A chase starts when a group next to one of the last
two moves has at most CHASE_LIBERTIES liberties and the areas give it to the other color by at least CHASE_START. It
goes on until the group is captured, or is broken when that share falls below CHASE_KEPT. The start is generous on
purpose: chasing a group that gets away is easier to understand than a sequence that stops for no visible reason.
"""

from __future__ import annotations

from kentogo.common.board import Board
from kentogo.common.shapes import neighbors
from kentogo.common.types import Move, Position, opponent
from kentogo.quiz.fight_judge import OWNED

CHASE_LIBERTIES = 2  # A chase starts with a group that has at most this many liberties.
CHASE_START = OWNED  # A chase starts when the areas give the group to the other color by at least this.
CHASE_KEPT = 0.25  # A chase is broken when the group's share falls below this (one reading may dip).
CHASE_GOING = "going"
CHASE_CAPTURED = "captured"
CHASE_BROKEN = "broken"

Point = tuple[int, int]
Areas = dict[Point, float]


def board_after(position: Position, moves: tuple[Move, ...]) -> Board:
    """Return the board of the position after the moves (a pass, or a move that is not allowed, is skipped)."""
    board = Board.from_position(position)
    for move in moves:
        if move.coord is not None and board.is_legal(move):
            board.play(move)
    return board


def _share(board: Board, stone: Point, areas: Areas, color: str) -> float:
    """Return how much the group of a stone belongs to color, on average (1: all of it)."""
    group = board.group_at(stone)
    sign = 1.0 if color == "B" else -1.0
    return sum(sign * areas.get(point, 0.0) for point in group) / len(group)


def _weak_stones(board: Board, moves: tuple[Move, ...]) -> list[Point]:
    """Return the stones on or next to the last two moves whose groups have at most CHASE_LIBERTIES liberties."""
    played = [move.coord for move in reversed(moves[-2:]) if move.coord is not None]
    points = [point for coord in played for point in (coord, *neighbors(board, coord))]
    return [
        point
        for point in points
        if board.stone_at(point) is not None and len(board.liberties(board.group_at(point))) <= CHASE_LIBERTIES
    ]


class ChaseTracker:
    """Follows the chase of one group at a time.

    Attributes:
        result: None before any chase, else CHASE_GOING, CHASE_CAPTURED or CHASE_BROKEN.
        share: How much the group looked at last belongs to the other color (rounded), or None.
    """

    def __init__(self, position: Position):
        """Start without a chase."""
        self._position = position
        self._stone: Point | None = None
        self._captor = ""
        self._broken_at = -1  # A chase broken after this many moves is not started again at once.
        self.result: str | None = None
        self.share: float | None = None

    @property
    def active(self) -> bool:
        """True while a group is being chased."""
        return self._stone is not None

    def update(self, moves: tuple[Move, ...], areas: Areas) -> None:
        """Start, keep or end the chase, from the areas of the position after the moves."""
        board = board_after(self._position, moves)
        if self._stone is None:
            if len(moves) != self._broken_at:
                self._start(board, moves, areas)
        elif board.stone_at(self._stone) != opponent(self._captor):
            self._stop(CHASE_CAPTURED)
        else:
            self._keep_or_break(board, moves, areas)

    def local_moves(self, moves: tuple[Move, ...], color: str) -> list[str]:
        """Return the legal moves (GTP) of color on the group's liberties and the empty points next to them."""
        board = board_after(self._position, moves)
        if self._stone is None or board.stone_at(self._stone) is None:
            return []
        liberties = board.liberties(board.group_at(self._stone))
        around = liberties | board.liberties(liberties)
        return sorted(move.gtp() for point in around if board.is_legal(move := Move(color, point)))

    def _start(self, board: Board, moves: tuple[Move, ...], areas: Areas) -> None:
        """Start a chase of the weak group that the areas give most to the other color, if it is given enough."""
        shares = {
            point: _share(board, point, areas, opponent(board.stone_at(point))) for point in _weak_stones(board, moves)
        }
        if not shares:
            return
        stone = max(shares, key=shares.get)
        self.share = round(shares[stone], 2)
        if shares[stone] >= CHASE_START:
            self._stone, self._captor, self.result = stone, opponent(board.stone_at(stone)), CHASE_GOING

    def _keep_or_break(self, board: Board, moves: tuple[Move, ...], areas: Areas) -> None:
        """Break the chase if the areas no longer give the group to the chaser."""
        share = _share(board, self._stone, areas, self._captor)
        self.share = round(share, 2)
        if share < CHASE_KEPT:
            self._broken_at = len(moves)
            self._stop(CHASE_BROKEN)

    def _stop(self, result: str) -> None:
        """End the chase."""
        self._stone, self.result = None, result
