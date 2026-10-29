"""Tests for kentogo.seichi.block_tidy."""

from kentogo.seichi.auto_fill import territory_areas
from kentogo.seichi.block_tidy import (
    Block,
    choose_goal,
    corners,
    find_blocks,
    plan_targets,
    tidy_by_blocks,
    tidy_color,
)

SIZE = 9


def board(top_stones: list, bottom_stones: list) -> dict:
    """A 9 x 9 board: black owns columns A-D, cut in two by a black row (row 5), with a black and a white wall.

    The top area is rows 1-4 and the bottom area rows 6-9 (16 points each, less the black stones given
    inside them). White owns columns G-J.
    """
    stones = {(x, 4): "B" for x in range(4)}
    for y in range(SIZE):
        stones[(4, y)] = "B"
        stones[(5, y)] = "W"
    for point in top_stones + bottom_stones:
        stones[point] = "B"
    return stones


TOP_STONES = [(1, 1), (2, 1), (1, 2)]  # The top area has 13 points.
BOTTOM_STONES = [(1, 6), (2, 6), (1, 7), (2, 7)]  # The bottom area has 12 points.


def parts(points: set) -> list[int]:
    """Return the sizes of the connected parts of the points, the smallest first."""
    points = set(points)
    sizes = []
    while points:
        stack = [points.pop()]
        count = 0
        while stack:
            x, y = stack.pop()
            count += 1
            for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if near in points:
                    points.remove(near)
                    stack.append(near)
        sizes.append(count)
    return sorted(sizes)


def black_sizes(stones: dict) -> list[int]:
    """Return the sizes of black's areas, the smallest first."""
    return sorted(len(area) for area in territory_areas(SIZE, stones, frozenset(), "B"))


def play(stones: dict, moves) -> dict:
    """Make the moves on a copy of the stones, checking that each one is possible."""
    stones = dict(stones)
    for move in moves:
        assert stones.get(move.source) == move.color and move.target not in stones
        stones[move.target] = stones.pop(move.source)
    return stones


def test_blocks_and_the_stones_that_can_move():
    """Stones inside an area can move; the walls (touching white, or both areas) cannot."""
    blocks = sorted(find_blocks(SIZE, board(TOP_STONES, BOTTOM_STONES), "B", frozenset()), key=lambda b: len(b.area))
    assert [len(block.area) for block in blocks] == [12, 13]
    assert blocks[0].movable == set(BOTTOM_STONES) and blocks[1].movable == set(TOP_STONES)


def test_a_small_block_gets_stones_from_a_larger_one_until_it_is_ten():
    """The block of 12 gets 2 stones from the block of 13, which becomes 15."""
    blocks = find_blocks(SIZE, board(TOP_STONES, BOTTOM_STONES), "B", frozenset())
    plan_targets(blocks)
    assert sorted((len(block.area), block.target) for block in blocks) == [(12, 10), (13, 15)]


def test_a_block_of_tens_gets_nothing():
    """A small block that is already ten is left as it is."""
    bottom = [(1, 6), (2, 6), (1, 7), (2, 7), (3, 7), (3, 8)]  # 10 points.
    blocks = find_blocks(SIZE, board(TOP_STONES, bottom), "B", frozenset())
    plan_targets(blocks)
    assert sorted((len(block.area), block.target) for block in blocks) == [(10, 10), (13, 13)]


def test_tidy_color_packs_the_whole_territory():
    """The territory (25 points) stays, and is cut in whole fives (the black stones next to white may move too)."""
    stones = board(TOP_STONES, BOTTOM_STONES)
    tidy = tidy_color(SIZE, stones, "B")
    after = play(stones, tidy.moves)
    assert len(tidy.territory) == 25 and not tidy.territory & set(after)
    assert all(after.get((5, y)) == "W" for y in range(SIZE))  # White's stones do not move.
    assert all(size % 5 == 0 for size in parts(tidy.territory))


def test_tidy_moves_keep_the_boundary_and_count_in_tens():
    """By blocks: the walls stay, the areas are 10 and 15, and moves inside an area come first."""
    stones = board(TOP_STONES, BOTTOM_STONES)
    moves = tidy_by_blocks(SIZE, stones, "B", frozenset())
    after = play(stones, moves)
    assert black_sizes(after) == [10, 15]
    assert all(after.get((4, y)) == "B" and after.get((x, 4)) == "B" for y in range(SIZE) for x in range(4))
    across = [i for i, move in enumerate(moves) if (move.source[1] < 4) != (move.target[1] < 4)]
    inside = [i for i, move in enumerate(moves) if i not in across]
    assert across and (not inside or max(inside) < min(across))
    assert tidy_by_blocks(SIZE, after, "W", frozenset()) == []  # White's area has no stone inside.


def test_the_goal_is_a_rectangle_near_the_block():
    """The top block of 15 becomes the 4 x 4 square of its rows with one point missing at a corner."""
    blocks = find_blocks(SIZE, board(TOP_STONES, BOTTOM_STONES), "B", frozenset())
    plan_targets(blocks)
    top = next(block for block in blocks if len(block.area) == 13)
    goal = choose_goal(top, SIZE, board(TOP_STONES, BOTTOM_STONES))
    xs, ys = {x for x, _ in goal}, {y for _, y in goal}
    assert len(goal) == 15 and xs == {0, 1, 2, 3} and ys == {0, 1, 2, 3}


def l_shaped(stones_inside: list) -> dict:
    """A 13 x 13 board: black owns columns A-D (all rows) and E-J of rows 1-3 (an L of 67 points).

    Black walls close it, with white outside them. stones_inside are black stones in the L.
    """
    size = 13
    black_points = {(x, y) for x in range(4) for y in range(size)} | {(x, y) for x in range(4, 9) for y in range(3)}
    stones = {}
    for x in range(size):
        for y in range(size):
            if (x, y) in black_points:
                continue
            near = any((x + dx, y + dy) in black_points for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            stones[(x, y)] = "B" if near else "W"
    for point in stones_inside:
        stones[point] = "B"
    return stones


def touches_white(stones: dict, point: tuple) -> bool:
    """Tell whether a stone has a white stone next to it (up, down, left or right)."""
    x, y = point
    return any(stones.get(near) == "W" for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))


def test_a_large_block_is_cut_into_tens_and_the_rest():
    """No rectangle fits the L of 57 points, so a line of its stones cuts it into 50 and 7."""
    inside = [(x, y) for x in (1, 2) for y in range(5, 10)]  # Ten stones (prisoners) inside: 57 points.
    stones = l_shaped(inside)
    moves = tidy_by_blocks(13, stones, "B", frozenset())
    after = play(stones, moves)
    sizes = sorted(len(area) for area in territory_areas(13, after, frozenset(), "B"))
    assert sizes == [7, 50]
    walls = [point for point in stones if stones[point] == "B" and touches_white(stones, point)]
    assert all(after.get(point) == "B" for point in walls)  # The stones that touch white stay.
    assert len(moves) <= len(inside)  # Each stone inside moves at most once.


def test_corners_of_shapes():
    """A rectangle has 4 corners, an L 6, and two points touching at a corner 8."""
    assert corners({(x, y) for x in range(3) for y in range(2)}) == 4
    assert corners({(0, 0), (1, 0), (0, 1)}) == 6
    assert corners({(0, 0), (1, 1)}) == 8


def test_a_block_that_cannot_be_cut_is_a_rectangle_and_the_rest():
    """A 5 x 4 rectangle with a tail of 3 points: no rectangle or cut fits, so it stays the rectangle and the rest."""
    rectangle = {(x, y) for x in range(5) for y in range(4)}
    tail = {(5, 0), (6, 0), (7, 0)}
    block = Block(rectangle | tail, set(), 23)
    assert choose_goal(block, 13, {}) == rectangle | tail
