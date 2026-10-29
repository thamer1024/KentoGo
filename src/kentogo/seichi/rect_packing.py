"""Pack the territory of a color into rectangles that are easy to count, as a person does in seichi.

People make the territory into rectangles of whole tens with walls of their own stones between
them, and leave the points that are not a whole ten in one small part. This module finds such
rectangles inside the room (the empty points of the territory and the stones that may be taken
away, see block_tidy).

The pieces (see Shapes):
- A rectangle with a side of 5 or 10, and the other side not longer than 10 (2 x 5, 4 x 5,
  3 x 10, 6 x 10, ...): its points are a whole number of fives.
- A rectangle with sides not longer than 8 and 1 to 4 points left out in its middle, in a line
  along its longer side, so that its points are a whole number of tens (3 x 7 - 1, 4 x 3 - 2,
  6 x 4 - 4, 8 x 3 - 4). The points left out get stones.
- The rest: one whole rectangle of the points left over the fives (the target % 5, 1 to 4).
- When no packing is found with these, more shapes are allowed (LOOSE): longer sides, and points
  left out as a run at a corner.

The rules:
- The pieces have the target number of points together, and no point is in two pieces.
- Two pieces never touch (up, down, left, right): there is a stone between them.
- Whole tens first, then fives, and only one rest.

The cost: each change (an empty point that gets a stone, or a stone that is taken away),
PIECE_COST for each piece (so that a few large rectangles are preferred), FIVE_COST for each point
of a piece of fives that are not whole tens, REST_COST for each point of a rest, and MISSING_COST
for each point left out.

The pieces are chosen by trial and error (greedy_pack: the best rectangles first, in many orders),
and by a small integer program (pack: scipy.optimize.milp, with the HiGHS solver) when that finds
nothing.
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import takewhile

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

Point = tuple[int, int]

FIVE = 5
TEN = 10
MAX_MISSING = 4  # The most points a piece may leave out.
LONGEST_WITH_HOLES = 8  # The longest side of a rectangle with points left out in its middle (9 is hard to count).
# The costs, in changes. The points in pieces of whole tens cost nothing, the points in pieces of
# whole fives cost some, and the points of the rest cost the most; then fewer pieces (larger
# areas); then fewer changes.
FIVE_COST = 4  # Each point of a piece of a whole number of fives that is not a whole number of tens.
REST_COST = 8  # Each point of a piece whose points are not a whole number of fives.
PIECE_COST = 6  # Each piece.
MISSING_COST = 1  # Each point left out of the rectangle of a piece.
SIZE_WEIGHTS = (0.5, 1.0, 0.2, 0.0)  # How much the size of a piece counts in greedy_score, tried in turn.
FIRST_TRIES = 12  # How many of the best pieces are tried as the first piece of the greedy packing.
RANDOM_TRIES = 300  # How many more greedy packings are tried with the scores shaken a little.
SHAKE = 3.0  # How much the scores are shaken (in changes).
SEED = 19  # The seed of the shaking, so that the same position always gives the same seichi.
TRY_SECONDS = 4.0  # Seconds that the trial and error may take for a color.
TIME_LIMIT = 3.0  # Seconds that the solver may take (the best packing found by then is used).


@dataclass(frozen=True)
class Shapes:
    """The shapes that a piece may have.

    Attributes:
        longest: The longest side of a whole rectangle of fives.
        corner: How many points may be left out as a run at a corner (0: none).
    """

    longest: int
    corner: int


STRICT = Shapes(TEN, 0)
LOOSE = Shapes(19, 3)
LEVELS = (STRICT, LOOSE)


@dataclass(frozen=True)
class Piece:
    """A candidate piece of territory.

    Attributes:
        points: The empty points of the piece at the end.
        rest: Whether it is the rest (its points are not a whole number of fives).
        missing: How many points of its rectangle are left out.
    """

    points: frozenset[Point]
    rest: bool
    missing: int


@dataclass(frozen=True)
class Packing:
    """The territory of an area at the end.

    Attributes:
        points: Its empty points.
        cost: Its cost (see the module docstring), counting each point of the area that gets a stone.
    """

    points: frozenset[Point]
    cost: float


def best_packing(area: set[Point], movable: set[Point], target: int, size: int) -> Packing | None:
    """Return the empty points at the end: rectangles of whole tens (or fives) and one small rest.

    The shapes of LEVELS are tried in turn: first by trial and error (greedy_pack), then with
    the integer program (pack).

    Args:
        area: The empty points of the territory.
        movable: The stones that may be taken away.
        target: How many points of territory there are at the end.
        size: The number of lines of the board.

    Returns:
        The packing, or None if none is found.
    """
    for shapes in LEVELS:
        packing = greedy_pack(area, movable, target, size, shapes) or pack(area, movable, target, size, shapes)
        if packing is not None:
            return packing
    return None


def pack(area: set[Point], movable: set[Point], target: int, size: int, shapes: Shapes = STRICT) -> Packing | None:
    """Return a packing found by the integer program (see the module docstring).

    Args:
        area: The empty points of the territory.
        movable: The stones that may be taken away.
        target: How many points of territory there are at the end (0: all the area gets stones).
        size: The number of lines of the board.
        shapes: The shapes that the pieces may have.

    Returns:
        The packing, or None if no packing is found in time.
    """
    if target <= 0:
        return Packing(frozenset(), len(area))
    pieces = candidate_pieces(area, movable, target, size, shapes)
    chosen = _solve(pieces, area | movable, area, target, size) if pieces else None
    if chosen is None:
        return None
    points = frozenset().union(*(piece.points for piece in chosen))
    return Packing(points, len(area) + sum(_piece_cost(piece, area) for piece in chosen))


def greedy_pack(
    area: set[Point], movable: set[Point], target: int, size: int, shapes: Shapes = STRICT
) -> Packing | None:
    """Return the best packing found by trial and error, as a person does: the best rectangles first.

    The pieces are taken in the order of greedy_score (see _greedy): for each weight of
    SIZE_WEIGHTS, starting with each of the first FIRST_TRIES pieces in turn, and then
    RANDOM_TRIES times with the scores shaken a little (for TRY_SECONDS at most). The packing
    with the least cost is used. None if none is found.
    """
    pieces = candidate_pieces(area, movable, target, size, shapes)
    orders = [_order(pieces, area, weight, None) for weight in SIZE_WEIGHTS]
    tries = [[first, *order] for order in orders for first in order[:FIRST_TRIES]]
    shaker = random.Random(SEED)
    best: Packing | None = None
    deadline = time.monotonic() + TRY_SECONDS
    for number in range(len(tries) + RANDOM_TRIES):
        if time.monotonic() > deadline:
            break
        order = tries[number] if number < len(tries) else _order(pieces, area, shaker.choice(SIZE_WEIGHTS), shaker)
        chosen = _greedy(order, target, size)
        if chosen is None:
            continue
        points = frozenset().union(*(piece.points for piece in chosen))
        packing = Packing(points, len(area) + sum(_piece_cost(piece, area) for piece in chosen))
        if best is None or packing.cost < best.cost:
            best = packing
    return best


def _order(pieces: list[Piece], area: set[Point], weight: float, shaker: random.Random | None) -> list[Piece]:
    """Return the pieces, the best first (see greedy_score), with the scores shaken by up to SHAKE if a shaker is given."""

    def key(piece: Piece) -> tuple:
        shake = shaker.uniform(-SHAKE, SHAKE) if shaker is not None else 0.0
        return (-(greedy_score(piece, area, weight) + shake), sorted(piece.points))

    return sorted(pieces, key=key)


def greedy_score(piece: Piece, area: set[Point], weight: float) -> float:
    """Return how good a piece is: the points of the territory it keeps, less the changes, and its size."""
    kept = len(piece.points & area)
    taken = len(piece.points - area)
    return kept - taken - piece.missing + weight * len(piece.points)


def _greedy(order: list[Piece], target: int, size: int) -> list[Piece] | None:
    """Take pieces in order, each apart from those taken: whole tens, then fives, and last one rest.

    None if the pieces cannot add up to the target.
    """
    blocked: set[Point] = set()
    chosen: list[Piece] = []
    remaining = target
    for unit, keep in ((TEN, target % TEN), (FIVE, target % FIVE), (target % FIVE, 0)):
        while unit and remaining - keep >= unit:
            allowed = set(range(unit, remaining - keep + 1, unit))
            piece = next((p for p in order if len(p.points) in allowed and not p.points & blocked), None)
            if piece is None:
                break
            chosen.append(piece)
            blocked |= piece.points | {near for point in piece.points for near in _neighbors(point, size)}
            remaining -= len(piece.points)
    return chosen if remaining == 0 else None


def candidate_pieces(
    area: set[Point], stones: set[Point], target: int, size: int, shapes: Shapes = STRICT
) -> list[Piece]:
    """Return the pieces that fit in the room (the area and the stones that may be taken away).

    See the module docstring for the shapes. A piece must be at least half territory already.
    """
    room = area | stones
    pieces: dict[frozenset[Point], Piece] = {}
    for x, y, width, height in _boxes(room, target + MAX_MISSING):
        box = frozenset((x + i, y + j) for i in range(width) for j in range(height))
        for left_out in _ways_to_leave_out(x, y, width, height, target, shapes):
            points = box - left_out
            if len(points) <= target and len(points & area) * 2 >= len(points):
                pieces[points] = Piece(points, len(points) % FIVE != 0, len(left_out))
    return list(pieces.values())


def _ways_to_leave_out(x: int, y: int, width: int, height: int, target: int, shapes: Shapes) -> list[frozenset[Point]]:
    """Return the points that may be left out of a rectangle to make it a piece (an empty set: the whole of it)."""
    count = width * height
    ways: list[frozenset[Point]] = []
    if count % FIVE == 0 and max(width, height) <= shapes.longest:
        ways.append(frozenset())
    elif count == target % FIVE:
        ways.append(frozenset())  # The rest.
    middle = _middle(x, y, width, height, count % TEN)
    if max(width, height) <= LONGEST_WITH_HOLES and middle is not None:
        ways.append(middle)
    for missing in range(1, shapes.corner + 1):
        if (count - missing) % FIVE == 0 and max(width, height) <= TEN:
            ways += _left_out(x, y, width, height, missing)
    return ways


def _middle(x: int, y: int, width: int, height: int, missing: int) -> frozenset[Point] | None:
    """Return `missing` points in the middle of a rectangle, in a line along its longer side.

    None if `missing` is not 1 to MAX_MISSING, or the line does not fit inside the rectangle
    (away from its sides).
    """
    if not 1 <= missing <= MAX_MISSING or min(width, height) < 3:
        return None
    inner_width, inner_height = width - 2, height - 2
    if inner_width >= inner_height:
        if inner_width < missing:
            return None
        start, row = x + 1 + (inner_width - missing) // 2, y + 1 + (inner_height - 1) // 2
        return frozenset((start + i, row) for i in range(missing))
    if inner_height < missing:
        return None
    start, column = y + 1 + (inner_height - missing) // 2, x + 1 + (inner_width - 1) // 2
    return frozenset((column, start + j) for j in range(missing))


def _boxes(room: set[Point], most: int) -> list[tuple[int, int, int, int]]:
    """Return the rectangles (x, y, width, height) that lie in the room, with up to `most` points."""
    corners = ((x, y, width) for x, y in sorted(room) for width in range(1, _run(room, x, y) + 1))
    return [(x, y, width, height) for x, y, width in corners for height in _heights(room, x, y, width, most)]


def _heights(room: set[Point], x: int, y: int, width: int, most: int) -> Iterator[int]:
    """Yield the heights 1, 2, ... of a rectangle from (x, y) while its top row is in the room (up to `most` points)."""
    return takewhile(
        lambda height: all((x + i, y + height - 1) in room for i in range(width)), range(1, most // width + 1)
    )


def _run(room: set[Point], x: int, y: int) -> int:
    """Return how many points of the room there are in a row from (x, y) to the right."""
    count = 0
    while (x + count, y) in room:
        count += 1
    return count


def _left_out(x: int, y: int, width: int, height: int, missing: int) -> list[frozenset[Point]]:
    """Return the ways to leave out `missing` points of a rectangle: a run at one end of one side."""
    if missing == 0:
        return [frozenset()]
    options = set()
    right, top = x + width - 1, y + height - 1
    if missing < width:
        for row in (y, top):
            options.add(frozenset((x + i, row) for i in range(missing)))
            options.add(frozenset((right - i, row) for i in range(missing)))
    if missing < height:
        for column in (x, right):
            options.add(frozenset((column, y + j) for j in range(missing)))
            options.add(frozenset((column, top - j) for j in range(missing)))
    return sorted(options, key=sorted)


def _solve(pieces: list[Piece], room: set[Point], area: set[Point], target: int, size: int) -> list[Piece] | None:
    """Choose the pieces with the integer program (see the module docstring). None if there is no solution."""
    rows: list[tuple[dict[int, float], float, float]] = []
    covering: dict[Point, list[int]] = {point: [] for point in room}
    for index, piece in enumerate(pieces):
        for point in piece.points:
            covering[point].append(index)
    rows.append(({i: len(p.points) for i, p in enumerate(pieces)}, target, target))
    rows += [({i: 1 for i in indexes}, 0, 1) for indexes in covering.values() if len(indexes) > 1]
    rows += _apart_rows(pieces, covering, size)
    cost = [_piece_cost(piece, area) for piece in pieces]
    result = milp(
        c=np.array(cost),
        constraints=_constraint(rows, len(pieces)),
        integrality=np.ones(len(pieces)),
        bounds=Bounds(0, 1),
        options={"time_limit": TIME_LIMIT},
    )
    if result.x is None:
        return None
    return [piece for piece, value in zip(pieces, result.x, strict=True) if value > 0.5]


def _apart_rows(
    pieces: list[Piece], covering: dict[Point, list[int]], size: int
) -> list[tuple[dict[int, float], float, float]]:
    """Return the rows that keep the pieces apart.

    For two points next to each other, a piece on one of them that does not cover the other,
    and such a piece on the other, are not chosen together (each point is in one piece at most).
    """
    rows = []
    for point, indexes in covering.items():
        for near in _neighbors(point, size):
            if near not in covering or near < point:
                continue
            only_here = [i for i in indexes if near not in pieces[i].points]
            only_there = [i for i in covering[near] if point not in pieces[i].points]
            if only_here and only_there:
                rows.append((dict.fromkeys(only_here + only_there, 1), 0, 1))
    return rows


def _piece_cost(piece: Piece, area: set[Point]) -> float:
    """Return the cost of choosing a piece: its changes (beyond leaving the block as it is), and its kind."""
    stones_taken = len(piece.points - area)
    points_kept = len(piece.points & area)
    count = len(piece.points)
    kind = count * (REST_COST if piece.rest else 0 if count % TEN == 0 else FIVE_COST)
    return stones_taken - points_kept + PIECE_COST + kind + MISSING_COST * piece.missing


def _constraint(rows: list[tuple[dict[int, float], float, float]], count: int) -> LinearConstraint:
    """Make the constraint of scipy from the rows (coefficients by piece, lowest, highest)."""
    data, row_index, column_index = [], [], []
    for number, (coefficients, _, _) in enumerate(rows):
        for column, value in coefficients.items():
            data.append(value)
            row_index.append(number)
            column_index.append(column)
    matrix = coo_matrix((data, (row_index, column_index)), shape=(len(rows), count)).tocsr()
    return LinearConstraint(matrix, [row[1] for row in rows], [row[2] for row in rows])


def _neighbors(point: Point, size: int) -> list[Point]:
    """Return the points next to a point (up, down, left, right) on the board."""
    x, y = point
    return [(a, b) for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if 0 <= a < size and 0 <= b < size]
