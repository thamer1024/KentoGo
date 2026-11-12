"""The names of the shapes of a move, and the cutting points, from the stones next to it (without KataGo).

A shape is named by the stones right next to the move, by these definitions (a stone of the player
is "own", one of the opponent "theirs"):

- CONNECT (ツギ): the move joins two or more own groups.
- CUT (キリ): two stones of theirs, of different groups, are next to the move in an L, and the point that
  closes the square is own.
- WEDGE (ワリコミ): stones of theirs on both sides of the move (left and right, or up and down).
- HANE (ハネ): an own stone diagonal to the move, where one of the two points between them is theirs and
  the other is empty.
- SAGARI (サガリ): from the only own stone next to the move, one line toward the edge, on the first or
  second line.
- NOBI (ノビ): from the only own stone next to the move, while a stone of theirs touches the move.
- TSUKE (ツケ): a stone of theirs next to the move, and no own stone.
- KOSUMI (コスミ): an own stone diagonal to the move, both points between them empty, no own stone next to it.
- IKKEN (一間トビ): an own stone two points away in a line with an empty point between, no own stone next to it.
- KEIMA (ケイマ): an own stone a knight's move away, no own stone next to it or diagonal to it.

One move can fit many names, which would make an explanation unclear, so they are narrowed down in
this order: CUT, WEDGE and CONNECT leave out TSUKE, HANE and NOBI; HANE leaves out TSUKE; a shape in
contact leaves out the shapes at a distance; of the shapes at a distance only the first of KOSUMI,
IKKEN and KEIMA is kept. Each name keeps the stones it is named from (shapes_of).

Cutting points (cut_points): an empty point between two own stones of different groups that stand
diagonally, while the other point between them is theirs.

The same rules as the user's own prototype (kento_prompt, shapes.py), written again for KentoGo.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.common.board import Board, Point
from kentogo.common.places import line_of
from kentogo.common.types import Move, opponent

CONNECT = "connect"
CUT = "cut"
WEDGE = "wedge"
HANE = "hane"
NOBI = "nobi"
SAGARI = "sagari"
TSUKE = "tsuke"
KOSUMI = "kosumi"
IKKEN = "ikken"
KEIMA = "keima"
IN_CONTACT = (CUT, WEDGE, CONNECT, HANE, NOBI, SAGARI, TSUKE)  # In the order of the names.
AT_DISTANCE = (KOSUMI, IKKEN, KEIMA)
KNIGHT_MOVES = ((1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1))


@dataclass(frozen=True)
class Shape:
    """A name of the shape of a move.

    Attributes:
        name: CONNECT, CUT, HANE, ...
        stones: The stones it is named from (for CUT and WEDGE, the stones of theirs; else own stones).
    """

    name: str
    stones: tuple[Point, ...]


def shapes_of(board: Board, move: Move) -> tuple[Shape, ...]:
    """Return the names of the shape of a move on the board before it, narrowed down (see the module).

    Args:
        board: The board before the move.
        move: The move (a pass has no shape).
    """
    if move.coord is None or board.stone_at(move.coord) is not None:
        return ()
    found: dict[str, list[Point]] = {}
    for name, stones in _all_shapes(board, move):
        kept = found.setdefault(name, [])
        kept += [stone for stone in stones if stone not in kept]
    _narrow(found)
    return tuple(Shape(name, tuple(found[name])) for name in IN_CONTACT + AT_DISTANCE if name in found)


def _narrow(found: dict[str, list[Point]]) -> None:
    """Leave out the names that a stronger name makes needless (see the module)."""
    if found.keys() & {CUT, WEDGE, CONNECT}:
        for name in (TSUKE, HANE, NOBI):
            found.pop(name, None)
    if HANE in found:
        found.pop(TSUKE, None)
    if found.keys() & set(IN_CONTACT):
        for name in AT_DISTANCE:
            found.pop(name, None)
        return
    first = next((name for name in AT_DISTANCE if name in found), None)
    for name in AT_DISTANCE:
        if name != first:
            found.pop(name, None)


def _all_shapes(board: Board, move: Move) -> list[tuple[str, list[Point]]]:
    """Return every name that fits the move, with its stones (before narrowing down)."""
    point, color = move.coord, move.color
    mine = [p for p in neighbors(board, point) if board.stone_at(p) == color]
    theirs = [p for p in neighbors(board, point) if board.stone_at(p) == opponent(color)]
    found = _contact_shapes(board, point, color, mine, theirs)
    found += _line_shapes(board, point, mine, theirs)
    found += _diagonal_shapes(board, point, color, mine)
    if not mine:
        found += _distant_shapes(board, point, color)
    return found


def _contact_shapes(
    board: Board, point: Point, color: str, mine: list[Point], theirs: list[Point]
) -> list[tuple[str, list[Point]]]:
    """Return CONNECT, TSUKE, WEDGE and CUT."""
    found = []
    if len({board.group_at(p) for p in mine}) >= 2:
        found.append((CONNECT, mine))
    if theirs and not mine:
        found.append((TSUKE, theirs))
    x, y = point
    for a, b in (((x - 1, y), (x + 1, y)), ((x, y - 1), (x, y + 1))):
        if a in theirs and b in theirs:
            found.append((WEDGE, [a, b]))
    for i, a in enumerate(theirs):
        for b in theirs[i + 1 :]:
            corner = (a[0] + b[0] - x, a[1] + b[1] - y)
            in_line = a[0] == b[0] or a[1] == b[1]
            if not in_line and board.stone_at(corner) == color and board.group_at(a) != board.group_at(b):
                found.append((CUT, [a, b]))
    return found


def _line_shapes(board: Board, point: Point, mine: list[Point], theirs: list[Point]) -> list[tuple[str, list[Point]]]:
    """Return SAGARI or NOBI from the only own stone next to the move."""
    if len(mine) != 1:
        return []
    own = mine[0]
    if line_of(point, board.size) == line_of(own, board.size) - 1 and line_of(point, board.size) <= 2:
        return [(SAGARI, [own])]
    return [(NOBI, [own])] if theirs else []


def _diagonal_shapes(board: Board, point: Point, color: str, mine: list[Point]) -> list[tuple[str, list[Point]]]:
    """Return HANE and KOSUMI from the own stones diagonal to the move."""
    found = []
    for diagonal in diagonals(board, point):
        if board.stone_at(diagonal) != color:
            continue
        between = {board.stone_at((diagonal[0], point[1])), board.stone_at((point[0], diagonal[1]))}
        if between == {opponent(color), None}:
            found.append((HANE, [diagonal]))
        elif between == {None} and not mine:
            found.append((KOSUMI, [diagonal]))
    return found


def _distant_shapes(board: Board, point: Point, color: str) -> list[tuple[str, list[Point]]]:
    """Return IKKEN and KEIMA (the move has no own stone next to it)."""
    found = []
    x, y = point
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        far, middle = (x + 2 * dx, y + 2 * dy), (x + dx, y + dy)
        if on_board(board, far) and board.stone_at(far) == color and board.stone_at(middle) is None:
            found.append((IKKEN, [far]))
    if any(board.stone_at(p) == color for p in diagonals(board, point)):
        return found
    for dx, dy in KNIGHT_MOVES:
        knight = (x + dx, y + dy)
        if on_board(board, knight) and board.stone_at(knight) == color:
            found.append((KEIMA, [knight]))
    return found


def cut_points(board: Board, color: str) -> list[Point]:
    """Return the cutting points of a player's stones, in order (see the module)."""
    found: set[Point] = set()
    for stone, owner in board.stones().items():
        if owner != color:
            continue
        for diagonal in diagonals(board, stone):
            point = _cut_between(board, stone, diagonal, color)
            if point is not None:
                found.add(point)
    return sorted(found)


def _cut_between(board: Board, stone: Point, diagonal: Point, color: str) -> Point | None:
    """Return the empty point between two diagonal own stones that can be cut there, or None."""
    if board.stone_at(diagonal) != color or board.group_at(stone) == board.group_at(diagonal):
        return None
    sides = ((stone[0], diagonal[1]), (diagonal[0], stone[1]))
    owners = [board.stone_at(side) for side in sides]
    if set(owners) != {opponent(color), None}:
        return None
    return sides[owners.index(None)]


def empty_triangle(board: Board, point: Point, color: str) -> bool:
    """True if a stone at a point makes an empty triangle: three own stones and an empty point in a 2x2 square."""
    x, y = point
    for left in (x - 1, x):
        for bottom in (y - 1, y):
            square = [(left + i, bottom + j) for i in (0, 1) for j in (0, 1)]
            if not all(on_board(board, p) for p in square):
                continue
            owners = [board.stone_at(p) for p in square]
            if owners.count(color) == 3 and owners.count(None) == 1:
                return True
    return False


def neighbors(board: Board, point: Point) -> list[Point]:
    """Return the points next to a point (up, down, left, right) on the board."""
    x, y = point
    return [p for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if on_board(board, p)]


def diagonals(board: Board, point: Point) -> list[Point]:
    """Return the points diagonally next to a point on the board."""
    x, y = point
    return [p for p in ((x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1), (x - 1, y - 1)) if on_board(board, p)]


def on_board(board: Board, point: Point) -> bool:
    """True if a point is on the board."""
    return 0 <= point[0] < board.size and 0 <= point[1] < board.size
