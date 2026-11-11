"""Tests for kentogo.katago.move_value (how big a move is, and what it does to the groups)."""

from kentogo.common.types import Move, Position
from kentogo.katago.move_value import BIG, URGENT, MoveValue, kind_of, move_value, read_move_value

SIZE = 3
ALL = [(x, y) for x in range(SIZE) for y in range(SIZE)]


def owners(black: list, white: list) -> dict:
    """Owners from black's side: 1 on the black points, -1 on the white ones, 0 elsewhere."""
    return {point: 1.0 if point in black else -1.0 if point in white else 0.0 for point in ALL}


def test_the_size_and_the_stones_killed_and_saved():
    """White's stone at (0, 0) dies after black's move; black's stone at (2, 2) lives. Black's view of the lead."""
    stones = {(0, 0): "W", (2, 2): "B"}
    after_pass = (-3.0, owners([], [(0, 0), (2, 2)]))
    after_move = (5.0, owners([(0, 0), (2, 2)], []))
    value = move_value(stones, "B", after_move, after_pass)
    assert (value.points, value.killed, value.saved) == (8.0, 1, 1)
    white = move_value(stones, "W", after_pass, after_move)  # White's view: the same, seen from white.
    assert white.points == 8.0 and white.killed == 1 and white.saved == 1


def test_urgent_or_big():
    """A move that changes the owners of stones is urgent; one that changes empty points is big."""
    stones = {(0, 0): "W"}
    on_stone = move_value(stones, "B", (1.0, owners([], [])), (0.0, owners([], [(0, 0)])))
    on_empty = move_value(stones, "B", (4.0, owners([(1, 1), (2, 2)], [(0, 0)])), (0.0, owners([], [(0, 0)])))
    assert kind_of(on_stone) == URGENT and on_stone.on_stones == 1.0
    assert kind_of(on_empty) == BIG and on_empty.on_stones == 0.0
    assert kind_of(MoveValue(3.0, 1, 0, 0.0)) == URGENT  # Killing stones is urgent.


class Engine:
    """Keeps the queries, so that a test answers them."""

    def __init__(self):
        self.queries, self.callbacks = [], []

    def query(self, request, callback):
        self.queries.append(request)
        self.callbacks.append(callback)
        return str(len(self.queries))


def test_read_move_value():
    """Both readings (after the move and after a pass) are asked with the owners; the value comes after both."""
    position = Position(SIZE, 0.5, "chinese", (Move.from_gtp("A1", "W"),), (), "B")
    engine, found, errors = Engine(), [], []
    read_move_value(engine, position, Move.from_gtp("B2", "B"), 50, 0.04, found.append, errors.append)
    assert [query["moves"] for query in engine.queries] == [[["B", "B2"]], [["B", "pass"]]]
    assert all(query["includeOwnership"] and query["maxVisits"] == 50 for query in engine.queries)
    engine.callbacks[0]({"rootInfo": {"scoreLead": 2.0}, "ownership": [1.0] * 9})
    assert found == []
    engine.callbacks[1]({"rootInfo": {"scoreLead": 0.0}, "ownership": [-1.0] * 9})
    assert found[0].points == 2.0 and found[0].killed == 1  # White's A1 is black's after B2.


def test_an_error_is_told_once():
    position = Position(SIZE, 0.5, "chinese", (), (), "B")
    engine, found, errors = Engine(), [], []
    read_move_value(engine, position, Move.from_gtp("B2", "B"), 50, None, found.append, errors.append)
    engine.callbacks[0]({"error": "broken"})
    engine.callbacks[1]({"error": "broken"})
    assert len(errors) == 1 and found == []
