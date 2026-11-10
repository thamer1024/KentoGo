"""Tests for kentogo.katago.quick_reading (shallow readings of positions, one at a time, kept by key)."""

from kentogo.common.types import Move, Position
from kentogo.katago.quick_reading import QUICK_VISITS, QuickReadings

POSITION = Position(9, 6.5, "japanese", (), (Move.from_gtp("E5", "B"),), "W")


class HeldEngine:
    """KataGo that keeps the queries, so that a test answers them; it can stop a query."""

    def __init__(self):
        self.queries = []
        self.callbacks = []
        self.terminated = []

    def query(self, request, callback):
        self.queries.append(request)
        self.callbacks.append(callback)
        return f"q{len(self.queries)}"

    def terminate(self, query_id):
        self.terminated.append(query_id)

    def answer(self, index: int, owner: float, lead: float = 1.5) -> None:
        self.callbacks[index]({"isDuringSearch": True})
        self.callbacks[index]({"isDuringSearch": False, "rootInfo": {"scoreLead": lead}, "ownership": [owner] * 81})


def test_a_position_is_read_shallowly_with_its_areas_and_kept():
    engine, readings, changes = HeldEngine(), QuickReadings(), []
    readings.ask(engine, "a", POSITION, 0.04, lambda: changes.append(1))
    readings.ask(engine, "a", POSITION, 0.04, lambda: changes.append(1))
    assert len(engine.queries) == 1 and engine.queries[0]["maxVisits"] == QUICK_VISITS
    assert engine.queries[0]["includeOwnership"] and engine.queries[0]["moves"] == [["B", "E5"]]
    engine.answer(0, 0.5, lead=2.5)
    reading = readings.get("a")
    assert changes == [1] and reading.lead == 2.5 and reading.ownership[(0, 0)] == 0.5
    readings.ask(engine, "a", POSITION, 0.04, lambda: None)
    assert len(engine.queries) == 1


def test_a_new_position_stops_the_reading_not_answered():
    engine, readings = HeldEngine(), QuickReadings()
    readings.ask(engine, "a", POSITION, None, lambda: None)
    readings.ask(engine, "b", POSITION, None, lambda: None)
    assert engine.terminated == ["q1"]
    engine.answer(0, 0.5)  # Dropped: that reading was stopped.
    engine.answer(1, -0.5)
    assert readings.get("a") is None and readings.get("b").ownership[(0, 0)] == -0.5


def test_errors_and_no_katago():
    engine, readings = HeldEngine(), QuickReadings()
    readings.ask(None, "a", POSITION, None, lambda: None)
    assert engine.queries == []
    readings.ask(engine, "a", POSITION, None, lambda: None)
    engine.callbacks[0]({"error": "broken"})
    readings.ask(engine, "a", POSITION, None, lambda: None)
    assert len(engine.queries) == 1 and readings.get("a") is None  # Not asked again.
