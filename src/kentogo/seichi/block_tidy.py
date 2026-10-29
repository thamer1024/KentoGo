"""Tidy the territory of a color, as a person does, keeping the territory where it is.

First the whole territory is packed into rectangles of whole tens (or fives) and a small rest,
with walls of the color's own stones between them (see rect_packing). The room for that is the
territory and the color's stones that touch only its territory, stones (of either color) and
the edge: such a stone may be taken away, and any point of the room may get a stone. As people
do, a stone of the wall next to the other player's stone may go; the territory then touches
the other player's stones, and its points are kept as the color's (the arrangement marks them,
see PackedTidy). The territory of the two players never touches, and never touches seki or dame.
When no packing is found (the solver has a time limit), the territory is tidied block by block
as follows.

A block is one area of the color's territory (connected empty points). The boundary (the
stones that touch the other player's stones, seki or dame) is never moved. The stones that
can be moved are the color's own stones inside a block: a stone that touches only that block,
its own color's stones and the edge (a prisoner put there, a stone sticking out of a wall, or a
stone of the wall that does not touch the other player).
Taking such a stone away makes its point part of the block; putting a stone on a point of the
block makes it one point smaller. So the territory of the color stays the same.

1. Counting in tens: a small block that is not a whole number of tens gets stones from the
   larger blocks, until it is a whole number of tens (for example 13 becomes 10, and 4 becomes
   0). A small block that is already a whole number of tens gets nothing. The points that are
   not a whole ten end in the large blocks that gave the stones.
2. Shaping: each block is made a rectangle (such as 2 x 5, or 4 x 5), or a rectangle with up to
   MAX_MISSING points missing at one end of a side (such as 3 x 7 - 1), when that needs only a few
   more moves than keeping its shape, and it stays where the block is. Sides of 5 or 10 are
   preferred. When no such rectangle fits, a block that is not a whole number of tens is cut
   in two with a straight line of its stones (across a row or a column of the block), as people
   do: one part a whole number of tens, and the other the points that are left (for example
   47 becomes 40 and 7); the stones for the line are the block's own movable stones (such as the
   prisoners put into it). When it cannot be cut either, the block is made a large rectangle (of
   at least TEN points, a whole number of tens or fives if it can) and the rest, put on one side
   of the rectangle (as a rectangle too if it can be) or around it, with the fewest changes and
   the fewest corners (for example 43 becomes 6 x 5 and 13). Otherwise the block keeps its
   shape: the points that get a stone are the nooks (see auto_fill), and the stones taken away
   are the ones that stick out the most.
3. The moves: first the moves inside each block, then the moves from one block to another;
   each time the shortest first. The stones are paired with the points so that they move as
   little as possible in total (see assignment).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import product

from kentogo.seichi.assignment import cheapest_pairs
from kentogo.seichi.auto_fill import TEN, nook_first, territory_areas
from kentogo.seichi.rect_packing import best_packing

Point = tuple[int, int]

MAX_MISSING = 4  # The most points that a rectangle may miss at one end of a side.
EXTRA_MOVES = 4  # Shaping may change this many more points than keeping the shape (or a quarter of the block).
REACH = 2  # The room's stones are this many steps from the area at most.
SPLIT_SHARE = 2  # Cutting a block may change up to this part of its points (1 / 2) more than keeping the shape.
REST_COST = 1  # How much one point of the rest counts against a rectangle (as one more change).
CORNER_COST = 3  # How much one corner of the outline counts (as changes): the fewer corners, the easier to count.
ODD_COST = {0: 0, 5: 1}  # How much a rectangle costs when its points are a whole number of tens (0), fives, or not.
OTHER_COST = 3


@dataclass(frozen=True)
class TidyMove:
    """One step of the seichi.

    Attributes:
        kind: "move" (a stone moved), or "place" (a prisoner put from the tray; source is target).
        color: The color of the stone.
        source: Where the stone was.
        target: Where it goes.
    """

    kind: str
    color: str
    source: Point
    target: Point


@dataclass
class Block:
    """One area of a color's territory.

    Attributes:
        area: The empty points of the area.
        movable: The color's stones that touch only this area, the color's stones and the edge.
        target: How many points of territory the block has at the end.
    """

    area: set[Point]
    movable: set[Point] = field(default_factory=set)
    target: int = 0


@dataclass(frozen=True)
class ColorTidy:
    """How the territory of a color is tidied.

    Attributes:
        moves: The moves of the color's stones, in order.
        territory: The points of the color's territory at the end, when it was packed (they may
            touch the other player's stones, so they must be marked as the color's); None when it
            was tidied block by block (the stones show the territory then).
    """

    moves: list[TidyMove]
    territory: frozenset[Point] | None


def tidy_color(
    size: int,
    stones: dict[Point, str],
    color: str,
    neutral: frozenset[Point] = frozenset(),
    other: frozenset[Point] = frozenset(),
) -> ColorTidy:
    """Return how to tidy the territory of a color (see the module docstring).

    The whole territory is packed into rectangles of tens when that can be found (see
    packed_tidy); otherwise it is tidied block by block (see tidy_by_blocks).

    Args:
        size: The number of lines of the board.
        stones: The stones on the board. It is not changed.
        color: The color whose territory is tidied.
        neutral: Points that are never territory (the points of seki).
        other: The other player's territory that only marks show (from packing it first).

    Returns:
        The moves, and the territory at the end when it was packed.
    """
    packed = packed_tidy(size, stones, color, neutral, other)
    if packed is not None:
        return packed
    return ColorTidy(tidy_by_blocks(size, stones, color, neutral), None)


def tidy_by_blocks(size: int, stones: dict[Point, str], color: str, neutral: frozenset[Point]) -> list[TidyMove]:
    """Return the moves that tidy the territory of a color block by block (steps 1 to 3 of the module docstring)."""
    blocks = find_blocks(size, stones, color, neutral)
    plan_targets(blocks)
    inside: list[tuple[Point, Point]] = []
    leaving: list[Point] = []
    needing: list[Point] = []
    for block in blocks:
        goal = choose_goal(block, size, stones)
        pairs, extra_sources, extra_targets = _pair(sorted(goal & block.movable), sorted(block.area - goal))
        inside += pairs
        leaving += extra_sources
        needing += extra_targets
    across, _, _ = _pair(leaving, needing)
    ordered = sorted(inside, key=_move_length) + sorted(across, key=_move_length)
    return [TidyMove("move", color, source, target) for source, target in ordered]


def packed_tidy(
    size: int, stones: dict[Point, str], color: str, neutral: frozenset[Point], other: frozenset[Point]
) -> ColorTidy | None:
    """Return the moves that make the whole territory of a color rectangles of tens (see rect_packing).

    The room is the territory and the color's stones near it (REACH) that touch only its
    territory, stones and the edge (see the module docstring and rect_packing.best_packing).
    None if no packing is found.
    """
    territory = set().union(*territory_areas(size, stones, frozenset(), color, neutral))
    room_stones = {
        point
        for point, stone in stones.items()
        if stone == color and _near(point, territory, REACH) and _inner(point, size, stones, territory, neutral | other)
    }
    packing = best_packing(territory, room_stones, len(territory), size)
    if packing is None:
        return None
    goal = packing.points
    pairs, _, _ = _pair(sorted(goal - territory), sorted(territory - goal))
    moves = [TidyMove("move", color, source, target) for source, target in sorted(pairs, key=_move_length)]
    return ColorTidy(moves, frozenset(goal))


def _near(point: Point, points: set[Point], reach: int) -> bool:
    """Tell whether a point is at most `reach` steps (along the lines) from one of the points."""
    x, y = point
    return any(
        (x + dx, y + dy) in points
        for dx in range(-reach, reach + 1)
        for dy in range(-(reach - abs(dx)), reach - abs(dx) + 1)
    )


def _inner(point: Point, size: int, stones: dict[Point, str], territory: set[Point], closed: frozenset[Point]) -> bool:
    """Tell whether a stone touches only the territory, stones and the edge (no seki and no other territory)."""
    return all(near in territory or (near in stones and near not in closed) for near in _neighbors(point, size))


def find_blocks(size: int, stones: dict[Point, str], color: str, neutral: frozenset[Point]) -> list[Block]:
    """Return the blocks of a color's territory, with the stones that can be moved in each one."""
    blocks = [Block(area, target=len(area)) for area in territory_areas(size, stones, frozenset(), color, neutral)]
    index = {point: number for number, block in enumerate(blocks) for point in block.area}
    for point, stone in stones.items():
        if stone != color:
            continue
        around = _neighbors(point, size)
        if any(p in neutral or (p not in index and stones.get(p) != color) for p in around):
            continue  # It touches the other player, seki or dame: it is part of the boundary.
        touched = {index[p] for p in around if p in index}
        if len(touched) == 1:
            blocks[touched.pop()].movable.add(point)
    return blocks


def plan_targets(blocks: list[Block]) -> None:
    """Set the points of each block at the end: small blocks become whole tens with stones of larger blocks.

    A block that has given stones does not get any, and a block that has got stones gives none.
    """
    capacity = [len(block.movable) for block in blocks]
    received: set[int] = set()
    gave: set[int] = set()
    for small in sorted(range(len(blocks)), key=lambda i: len(blocks[i].area)):
        need = blocks[small].target % TEN
        if need == 0 or small in gave:
            continue
        givers = [
            i
            for i in sorted(range(len(blocks)), key=lambda i: -len(blocks[i].area))
            if len(blocks[i].area) > len(blocks[small].area) and capacity[i] > 0 and i not in received
        ]
        if sum(capacity[i] for i in givers) < need:
            continue
        for giver in givers:
            count = min(capacity[giver], need)
            capacity[giver] -= count
            blocks[giver].target += count
            blocks[small].target -= count
            need -= count
            gave.add(giver)
            if need == 0:
                break
        received.add(small)


def choose_goal(block: Block, size: int, stones: dict[Point, str]) -> set[Point]:
    """Return the empty points of a block at the end (see the module docstring).

    A rectangle near the block if it is cheap, else the block cut in tens and the rest if that
    is cheap, else a large rectangle and the rest, else its own shape.
    """
    keep = _keep_shape(block, size, stones)
    kept = len(_changes(block, keep))
    rectangle = _best_rectangle(block, size)
    if rectangle is not None and len(_changes(block, rectangle)) <= kept + max(EXTRA_MOVES, block.target // 4):
        return rectangle
    cut = _best_cut(block, size)
    if cut is not None and len(_changes(block, cut)) <= kept + max(EXTRA_MOVES, block.target // SPLIT_SHARE):
        return cut
    with_rest = _rectangle_and_rest(block, size)
    return with_rest if with_rest is not None else keep


def _keep_shape(block: Block, size: int, stones: dict[Point, str]) -> set[Point]:
    """Return the block's own shape with its target number of points: nooks filled, or stones sticking out taken."""
    change = block.target - len(block.area)
    if change < 0:
        return block.area - set(nook_first(block.area, -change, size, stones))
    by_sticking_out = sorted(block.movable, key=lambda p: (-sum(n in block.area for n in _neighbors(p, size)), p))
    return block.area | set(by_sticking_out[:change])


def _changes(block: Block, goal: set[Point]) -> set[Point]:
    """Return the points of a block that change: stones taken away, and empty points that get a stone."""
    return (goal & block.movable) | (block.area - goal)


def _best_rectangle(block: Block, size: int) -> set[Point] | None:
    """Return the rectangle (perhaps with a few points missing) with the target points that needs the fewest moves.

    It must lie inside the block and its movable stones. Whole rectangles come first, then the
    fewest moves, then sides of 5 or 10. None if no such rectangle fits, or the target is 0.
    """
    if block.target == 0:
        return None
    return _best_shape(_rectangle_candidates(block, size))


def _rectangle_candidates(block: Block, size: int) -> Iterator[tuple[tuple, set[Point]]]:
    """Yield (key, shape) for each rectangle with the target points, perhaps with a few points missing."""
    count = block.target
    room = block.area | block.movable
    for x, y, width, height in _fitting_boxes(room, _sizes(count, size)):
        box = _box(x, y, width, height)
        for missing in _missing_options(x, y, width, height, width * height - count):
            shape = box - missing
            key = (bool(missing), len(_changes(block, shape)), width % 5 != 0 and height % 5 != 0, x, y)
            yield key, shape


def _best_shape(candidates: Iterable[tuple[tuple, set[Point]]]) -> set[Point] | None:
    """Return the shape with the lowest key (the first one of equal keys), or None if there are none."""
    best = min(candidates, key=lambda candidate: candidate[0], default=None)
    return best[1] if best is not None else None


def _fitting_boxes(room: set[Point], sizes: Iterable[tuple[int, int]]) -> Iterator[tuple[int, int, int, int]]:
    """Yield the rectangles (x, y, width, height) of the sizes that lie inside the room, size by size."""
    low_x, high_x = min(x for x, _ in room), max(x for x, _ in room)
    low_y, high_y = min(y for _, y in room), max(y for _, y in room)
    for width, height in sizes:
        corners = product(range(low_x, high_x - width + 2), range(low_y, high_y - height + 2))
        yield from ((x, y, width, height) for x, y in corners if _box(x, y, width, height) <= room)


def _box(x: int, y: int, width: int, height: int) -> set[Point]:
    """Return the points of a rectangle with its lower left corner at (x, y)."""
    return {(x + i, y + j) for i, j in product(range(width), range(height))}


def _rectangle_and_rest(block: Block, size: int) -> set[Point] | None:
    """Return a large rectangle and the rest of the points on one side of it, with the fewest changes.

    The rectangle has at least TEN points and at least as many as the rest. Each change, each
    point of the rest (REST_COST), and a rectangle that is not a whole number of tens (ODD_COST)
    count against it. None if no such rectangle fits.
    """
    return _best_shape(_rest_candidates(block, size))


def _rest_candidates(block: Block, size: int) -> Iterator[tuple[tuple, set[Point]]]:
    """Yield (key, shape) for each large rectangle with the rest of the points in a region beside it."""
    for corner, width, height, region in _rest_places(block, size):
        rest = block.target - width * height
        part = _rest_part(block, region, rest, size)
        if part is None:
            continue
        shape = _box(corner[0], corner[1], width, height) | part
        cost = len(_changes(block, shape)) + REST_COST * rest + CORNER_COST * corners(shape) + _odd_cost(width * height)
        yield (cost, corner, width, height, sorted(part)), shape


def _rest_places(block: Block, size: int) -> Iterator[tuple[Point, int, int, set[Point]]]:
    """Yield (corner, width, height, region) for each rectangle large enough, and each region for the rest.

    The rectangle has at least TEN points and at least as many as the rest, and leaves a rest.
    """
    room, count = block.area | block.movable, block.target
    for corner, width, height in _rectangles(room, size, count):
        rest = count - width * height
        if rest == 0 or width * height < max(TEN, rest):
            continue
        box = _box(corner[0], corner[1], width, height)
        yield from ((corner, width, height, region) for region in _rest_regions(room, box))


def _rectangles(room: set[Point], size: int, most: int) -> list[tuple[Point, int, int]]:
    """Return the rectangles (lower left corner, width, height) inside the room with up to `most` points."""
    low_x, high_x = min(x for x, _ in room), max(x for x, _ in room)
    low_y, high_y = min(y for _, y in room), max(y for _, y in room)
    widths = range(1, min(size, high_x - low_x + 1) + 1)
    sizes = ((w, h) for w in widths for h in range(1, min(size, high_y - low_y + 1, most // w) + 1))
    return [((x, y), width, height) for x, y, width, height in _fitting_boxes(room, sizes)]


def _rest_regions(room: set[Point], box: set[Point]) -> list[set[Point]]:
    """Return where the rest of a block may be: beyond each side of the rectangle, or anywhere out of it."""
    regions = [{point for point in room if _beyond(point, box, side)} for side in range(4)]
    return [region for region in regions if region] + [room - box]


def _rest_part(block: Block, region: set[Point], rest: int, size: int) -> set[Point] | None:
    """Return `rest` points of a block in a region.

    A rectangle of the region if one fits, else the region's points of the block without its
    nooks, else those points with the movable stones of the region that touch the most points of
    the block. None if the region is too small.
    """
    pool = block.area & region
    stones = block.movable & region
    if pool:
        rectangle = _best_rectangle(Block(pool, stones, rest), size)
        if rectangle is not None:
            return rectangle
    if rest <= len(pool):
        outside = {(x, y): "B" for x in range(size) for y in range(size) if (x, y) not in pool}
        return pool - set(nook_first(pool, len(pool) - rest, size, outside))
    if len(pool) + len(stones) < rest:
        return None
    by_inside = sorted(stones, key=lambda p: (-sum(n in block.area for n in _neighbors(p, size)), p))
    return pool | set(by_inside[: rest - len(pool)])


def _beyond(point: Point, box: set[Point], side: int) -> bool:
    """Tell whether a point is beyond a rectangle on a side (0 left, 1 right, 2 below, 3 above)."""
    axis = side // 2
    values = [p[axis] for p in box]
    if side % 2 == 0:
        return point[axis] < min(values)
    return point[axis] > max(values)


def corners(shape: set[Point]) -> int:
    """Return the number of corners of the outline of a shape (4 for a rectangle): the fewer, the easier to count."""
    count = 0
    for x, y in {(x + dx, y + dy) for x, y in shape for dx in (0, 1) for dy in (0, 1)}:
        cells = [(x - 1, y - 1) in shape, (x, y - 1) in shape, (x, y) in shape, (x - 1, y) in shape]
        inside = sum(cells)
        if inside in (1, 3):
            count += 1
        elif inside == 2 and cells[0] == cells[2]:
            count += 2
    return count


def _odd_cost(count: int) -> int:
    """Return how much a rectangle of `count` points costs for not being a whole number of tens (or fives)."""
    return ODD_COST.get(count % TEN, OTHER_COST)


def _best_cut(block: Block, size: int) -> set[Point] | None:
    """Return the block cut by a straight line into a whole number of tens and the rest, with the fewest changes.

    None if the block is a whole number of tens (or smaller than ten), or no line can cut it so.
    """
    if block.target < TEN or block.target % TEN == 0:
        return None
    return _best_shape(_cut_candidates(block, size))


def _cut_candidates(block: Block, size: int) -> Iterator[tuple[tuple, set[Point]]]:
    """Yield (key, shape) for each straight cut that leaves the tens on one side and the rest on the other."""
    count = block.target
    rest = count % TEN
    for axis, line, tens_part, rest_part in _cuts(block.area | block.movable):
        shape = _cut_shape(tens_part, count - rest, rest_part, rest, size)
        if shape is not None:
            yield (len(_changes(block, shape)), axis, line), shape


def _cuts(room: set[Point]) -> Iterator[tuple[int, int, set[Point], set[Point]]]:
    """Yield (axis, line, one side, other side) for each straight line through the room, both sides each way."""
    for axis in (0, 1):
        for line in sorted({point[axis] for point in room}):
            low = {p for p in room if p[axis] < line}
            high = {p for p in room if p[axis] > line}
            yield axis, line, low, high
            yield axis, line, high, low


def _cut_shape(tens_part: set[Point], tens: int, rest_part: set[Point], rest: int, size: int) -> set[Point] | None:
    """Return the empty points of the two parts of a cut block: the tens on one side, the rest on the other.

    Each part gives up its nooks (see auto_fill.nook_first) until it has its number of points.
    None if a part is too small.
    """
    if len(tens_part) < tens or len(rest_part) < rest:
        return None
    shape = set()
    for part, keep in ((tens_part, tens), (rest_part, rest)):
        outside = {(x, y): "B" for x in range(size) for y in range(size) if (x, y) not in part}
        shape |= part - set(nook_first(part, len(part) - keep, size, outside))
    return shape


def _sizes(count: int, size: int) -> list[tuple[int, int]]:
    """Return the (width, height) of the rectangles with count to count + MAX_MISSING points that fit the board."""
    sides = range(1, size + 1)
    return [(w, h) for w, h in product(sides, sides) if count <= w * h <= count + MAX_MISSING]


def _missing_options(x: int, y: int, width: int, height: int, missing: int) -> list[frozenset[Point]]:
    """Return the ways to leave out `missing` points of a rectangle: a run at one end of one side."""
    if missing == 0:
        return [frozenset()]
    options = []
    right, top = x + width - 1, y + height - 1
    if missing < width:
        for row in (y, top):
            options.append(frozenset((x + i, row) for i in range(missing)))
            options.append(frozenset((right - i, row) for i in range(missing)))
    if missing < height:
        for column in (x, right):
            options.append(frozenset((column, y + j) for j in range(missing)))
            options.append(frozenset((column, top - j) for j in range(missing)))
    return options


def _pair(sources: list[Point], targets: list[Point]) -> tuple[list[tuple[Point, Point]], list[Point], list[Point]]:
    """Pair stones with points so that they move as little as possible in total (as many pairs as possible).

    Returns:
        The pairs (source, target), the sources left without a target, and the targets left without a source.
    """
    count = max(len(sources), len(targets))
    if count == 0:
        return [], [], []
    cost = [
        [_distance(sources[i], targets[j]) if i < len(sources) and j < len(targets) else 0 for j in range(count)]
        for i in range(count)
    ]
    pairs, used_targets, extra_sources = [], set(), []
    for i, j in enumerate(cheapest_pairs(cost)):
        if i >= len(sources):
            continue
        if j < len(targets):
            pairs.append((sources[i], targets[j]))
            used_targets.add(j)
        else:
            extra_sources.append(sources[i])
    extra_targets = [target for j, target in enumerate(targets) if j not in used_targets]
    return pairs, extra_sources, extra_targets


def _move_length(move: tuple[Point, Point]) -> tuple[int, Point, Point]:
    """The order of moves: the shortest first (then by the points, so that it is always the same)."""
    return _distance(*move), *move


def _distance(a: Point, b: Point) -> int:
    """The number of steps between two points (along the lines)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors(point: Point, size: int) -> list[Point]:
    """Return the points next to a point (up, down, left, right) on the board."""
    x, y = point
    return [(a, b) for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if 0 <= a < size and 0 <= b < size]
