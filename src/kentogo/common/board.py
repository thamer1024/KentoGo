"""The board: place stones, remove captured stones, and check if a move is legal.

The board works in the same way as KaTrain's board:

- A stone cannot immediately take back a single stone in a ko (under all rules).
- A suicide of a single stone is never allowed.
- A suicide of two or more stones is allowed only when the rules allow it
  (see common.rules). The stones are then removed from the board.

Like KaTrain, the board does not check superko (repeating an earlier position
in a longer cycle). KataGo checks it when it analyzes moves.
"""

from __future__ import annotations

from collections.abc import Iterator

from kentogo.common.rules import allows_suicide, normalize_rules
from kentogo.common.types import Move, Position, opponent

Point = tuple[int, int]


class IllegalMoveError(ValueError):
    """Raised when a move is not allowed on the board."""


class Board:
    """The stones on a board, which change as moves are played.

    Attributes:
        size: Size of the board.
        allow_suicide: True if a suicide of two or more stones is allowed.
        captures: Number of stones taken by each color, as {"B": n, "W": n}.
        ko_point: The point where the next player cannot play because of ko, or None.
    """

    def __init__(self, size: int, allow_suicide: bool = False):
        """Make an empty board.

        Args:
            size: Size of the board (19 for a 19x19 board).
            allow_suicide: True if the rules allow a suicide of two or more stones.
        """
        self.size = size
        self.allow_suicide = allow_suicide
        self.captures = {"B": 0, "W": 0}
        self.ko_point: Point | None = None
        self._stones: dict[Point, str] = {}

    @classmethod
    def from_position(cls, position: Position) -> Board:
        """Make the board of a position: place the setup stones, then play the moves.

        The rules of the position decide whether suicide is allowed.

        Args:
            position: The position.

        Returns:
            The board.

        Raises:
            IllegalMoveError: If a move of the position is not allowed.
        """
        board = cls(position.size, allows_suicide(normalize_rules(position.rules)))
        for stone in position.setup:
            if stone.coord is not None:
                board._stones[stone.coord] = stone.color
        for move in position.moves:
            board.play(move)
        return board

    def copy(self) -> Board:
        """Return a copy that can be changed without changing this board."""
        board = Board(self.size, self.allow_suicide)
        board.captures = dict(self.captures)
        board.ko_point = self.ko_point
        board._stones = dict(self._stones)
        return board

    def stone_at(self, point: Point) -> str | None:
        """Return the color of the stone at a point ("B" or "W"), or None if it is empty."""
        return self._stones.get(point)

    def stones(self) -> dict[Point, str]:
        """Return all stones as a new dict from point to color."""
        return dict(self._stones)

    def group_at(self, point: Point) -> frozenset[Point]:
        """Return the stones connected to the stone at a point (same color), or an empty set if the point is empty."""
        return frozenset(self._group(point)) if point in self._stones else frozenset()

    def liberties(self, group: frozenset[Point] | set[Point]) -> frozenset[Point]:
        """Return the empty points next to the stones of a group."""
        return frozenset(n for stone in group for n in self._neighbors(stone) if n not in self._stones)

    def is_legal(self, move: Move) -> bool:
        """Return True if the move is allowed on this board now."""
        try:
            self.copy().play(move)
        except IllegalMoveError:
            return False
        return True

    def play(self, move: Move) -> list[Point]:
        """Play a move: place the stone and remove the captured stones.

        Args:
            move: The move. A pass is allowed and only clears the ko point.

        Returns:
            The points of the stones removed from the board. These are the
            captured stones of the opponent, or the player's own stones
            after an allowed suicide.

        Raises:
            IllegalMoveError: If the point is outside the board or not empty,
                or the move takes back a ko, or it is a suicide that is not allowed.
        """
        if move.coord is None:
            self.ko_point = None
            return []
        point = move.coord
        if not self._on_board(point):
            raise IllegalMoveError(f"{move.gtp()} is outside the board")
        if point in self._stones:
            raise IllegalMoveError(f"{move.gtp()} is not empty")
        if point == self.ko_point:
            raise IllegalMoveError(f"{move.gtp()} takes back a ko")

        self._stones[point] = move.color
        captured = self._remove_captured_neighbors(point, opponent(move.color))
        own_group = self._group(point)
        if not self._has_liberty(own_group):
            return self._play_suicide(move, own_group)

        self.captures[move.color] += len(captured)
        self.ko_point = self._new_ko_point(point, captured)
        return captured

    def _play_suicide(self, move: Move, own_group: set[Point]) -> list[Point]:
        """Finish a move whose own group has no liberty after it was placed.

        Args:
            move: The move, already placed on the board.
            own_group: The group of the new stone.

        Returns:
            The points of the player's stones that were removed.

        Raises:
            IllegalMoveError: If the suicide is not allowed. The new stone is
                taken away first, so the board is the same as before the move.
        """
        if len(own_group) == 1 or not self.allow_suicide:
            del self._stones[move.coord]
            raise IllegalMoveError(f"{move.gtp()} is a suicide")
        for stone in own_group:
            del self._stones[stone]
        self.captures[opponent(move.color)] += len(own_group)
        self.ko_point = None
        return sorted(own_group)

    def _remove_captured_neighbors(self, point: Point, color: str) -> list[Point]:
        """Remove the groups of the given color next to point that have no liberty."""
        captured: list[Point] = []
        for neighbor in self._neighbors(point):
            if self._stones.get(neighbor) == color and neighbor not in captured:
                group = self._group(neighbor)
                if not self._has_liberty(group):
                    captured.extend(group)
        for stone in captured:
            del self._stones[stone]
        return captured

    def _new_ko_point(self, point: Point, captured: list[Point]) -> Point | None:
        """Find the ko point after a move at point that captured the given stones.

        It is a ko only when one stone was captured, and the new stone is alone
        with exactly one liberty (the point where the captured stone was).
        """
        if len(captured) != 1:
            return None
        group = self._group(point)
        liberties = {n for stone in group for n in self._neighbors(stone) if n not in self._stones}
        if len(group) == 1 and liberties == {captured[0]}:
            return captured[0]
        return None

    def _group(self, point: Point) -> set[Point]:
        """Return the stones that are connected to the stone at point (same color)."""
        color = self._stones[point]
        group = {point}
        stack = [point]
        while stack:
            for neighbor in self._neighbors(stack.pop()):
                if neighbor not in group and self._stones.get(neighbor) == color:
                    group.add(neighbor)
                    stack.append(neighbor)
        return group

    def _has_liberty(self, group: set[Point]) -> bool:
        """Return True if at least one stone of the group has an empty point next to it."""
        return any(n not in self._stones for stone in group for n in self._neighbors(stone))

    def _neighbors(self, point: Point) -> Iterator[Point]:
        """Yield the points next to point (up, down, left, right) that are on the board."""
        x, y = point
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self._on_board(neighbor):
                yield neighbor

    def _on_board(self, point: Point) -> bool:
        """Return True if the point is on the board."""
        x, y = point
        return 0 <= x < self.size and 0 <= y < self.size
