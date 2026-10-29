"""Tests for kentogo.seichi.rect_packing."""

from kentogo.seichi.rect_packing import _middle, candidate_pieces, greedy_pack, pack

SIZE = 13


def rectangle(x: int, y: int, width: int, height: int) -> set:
    """Return the points of a rectangle."""
    return {(x + i, y + j) for i in range(width) for j in range(height)}


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


def test_a_corner_stone_moves_to_the_middle():
    """3 x 7 with a stone in a corner is 20 points: the stone goes to the middle (3 x 7 - 1), as people count it."""
    area = rectangle(0, 0, 3, 7) - {(0, 0)}
    expected = rectangle(0, 0, 3, 7) - {(1, 3)}
    assert pack(area, {(0, 0)}, 20, SIZE).points == expected
    assert greedy_pack(area, {(0, 0)}, 20, SIZE).points == expected


def test_the_middle_points_left_out():
    """The examples of people: 3 x 7 - 1, 4 x 3 - 2, 6 x 4 - 4 and 8 x 3 - 4 leave out points in the middle."""
    assert _middle(0, 0, 3, 7, 1) == {(1, 3)}
    assert _middle(0, 0, 4, 3, 2) == {(1, 1), (2, 1)}
    assert _middle(0, 0, 6, 4, 4) == {(1, 1), (2, 1), (3, 1), (4, 1)}
    assert _middle(0, 0, 8, 3, 4) == {(2, 1), (3, 1), (4, 1), (5, 1)}
    assert _middle(0, 0, 2, 7, 1) is None  # No middle away from the sides.


def test_long_and_odd_rectangles_are_not_pieces():
    """2 x 15 (a side of 15) and 9 x 7 - 3 (no side of 5 or 10, points left out at a corner) are not used."""
    sizes = {len(piece.points) for piece in candidate_pieces(rectangle(0, 0, 2, 15), set(), 30, SIZE)}
    assert 30 not in sizes and 20 in sizes
    shapes = {frozenset(piece.points) for piece in candidate_pieces(rectangle(0, 0, 9, 7), set(), 60, SIZE)}
    assert not any(len(shape) == 60 for shape in shapes)
    assert any(len(shape) == 30 for shape in shapes)  # 5 x 6


def test_twelve_points_become_ten_and_two_with_a_wall_between():
    """2 x 6 empty points and a row of 2 stones: 2 x 5, a wall of stones, and the 2 points that are left."""
    area = rectangle(0, 0, 2, 6)
    stones = rectangle(0, 6, 2, 1)
    for packing in (pack(area, stones, 12, SIZE), greedy_pack(area, stones, 12, SIZE)):
        assert packing is not None and parts(packing.points) == [2, 10]


def test_no_packing_without_room_for_a_wall():
    """12 points in a row of 2 x 6 cannot be 10 and 2 with a wall between them."""
    assert pack(rectangle(0, 0, 2, 6), set(), 12, SIZE) is None
    assert greedy_pack(rectangle(0, 0, 2, 6), set(), 12, SIZE) is None


def test_pieces_are_fives_or_small_rests():
    """The pieces are whole fives (perhaps with points left out), or whole rectangles smaller than ten."""
    pieces = candidate_pieces(rectangle(0, 0, 4, 4), set(), 16, SIZE)
    assert pieces
    assert all(len(piece.points) % 5 == 0 or (piece.rest and len(piece.points) < 10) for piece in pieces)


def test_greedy_takes_tens_then_fives_then_the_rest():
    """43 points in a 9 x 5 room with two stones: 40 (8 x 5), a wall, and the 3 points left over."""
    room = rectangle(0, 0, 10, 5)
    stones = {(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (9, 3), (9, 4)}
    packing = greedy_pack(room - stones, stones, 43, SIZE)
    assert packing is not None and parts(packing.points) == [3, 40]


def test_a_whole_area_needs_no_stone_to_move():
    """A 2 x 5 area is already 10: packing it changes nothing."""
    area = rectangle(0, 0, 2, 5)
    assert greedy_pack(area, set(), 10, SIZE).points == area
