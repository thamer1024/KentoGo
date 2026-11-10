"""Tests for kentogo.quiz.quick_areas (the shallow areas of every position of a sequence after the answer)."""

from test_standings import make_session

from kentogo.katago.quick_reading import QUICK_VISITS
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.quick_areas import QuickAreas
from kentogo.quiz.session import QuizSession
from kentogo.quiz.transform import BoardTransform


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

    def answer(self, index: int, owner: float) -> None:
        """Answer a query with the same owner on every point (first a report during the search)."""
        self.callbacks[index]({"isDuringSearch": True})
        self.callbacks[index]({"isDuringSearch": False, "rootInfo": {"scoreLead": 1.0}, "ownership": [owner] * 81})


def test_each_shown_position_is_read_shallowly_and_kept(tmp_path):
    """The shown position (here the end of the sequence) is read with QUICK_VISITS; going back reads that one too."""
    session, engine = make_session(tmp_path), HeldEngine()
    areas, changes = QuickAreas(session), []
    areas.ask(engine, 0.04, lambda: changes.append(1))
    query = engine.queries[0]
    assert query["maxVisits"] == QUICK_VISITS and query["includeOwnership"]
    assert query["moves"][-2:] == [["B", "E5"], ["W", "D4"]]  # The sequence played to its last move.
    areas.ask(engine, 0.04, lambda: changes.append(1))
    assert len(engine.queries) == 1  # Already asked.
    engine.answer(0, 0.7)
    assert changes == [1] and areas.shown()[(0, 0)] == 0.7
    session.step_back()
    assert areas.shown() is None
    areas.ask(engine, 0.04, lambda: changes.append(1))
    assert engine.queries[1]["moves"][-1] == ["B", "E5"]
    session.step_forward()
    areas.ask(engine, 0.04, lambda: changes.append(1))
    assert len(engine.queries) == 2 and areas.shown()[(0, 0)] == 0.7  # Kept: not asked again.


def test_a_reading_not_answered_is_stopped_when_the_user_moves(tmp_path):
    session, engine = make_session(tmp_path), HeldEngine()
    areas = QuickAreas(session)
    areas.ask(engine, None, lambda: None)
    session.step_back()
    areas.ask(engine, None, lambda: None)
    assert engine.terminated == ["q1"] and len(engine.queries) == 2
    engine.answer(0, 0.9)  # The answer of the stopped reading is dropped.
    session.step_forward()
    assert areas.shown() is None


def test_the_areas_follow_the_board(tmp_path):
    """With the colors swapped, the owners are from the other side."""
    session, engine = make_session(tmp_path, BoardTransform(0, swap_colors=True)), HeldEngine()
    areas = QuickAreas(session)
    areas.ask(engine, None, lambda: None)
    engine.answer(0, 0.7)
    assert areas.shown()[(0, 0)] == -0.7


def test_nothing_is_read_before_the_answer_or_without_katago(tmp_path):
    session = make_session(tmp_path)
    fresh = QuizSession(session.problem, ScoringPolicy(), BoardTransform())
    engine = HeldEngine()
    QuickAreas(fresh).ask(engine, None, lambda: None)
    QuickAreas(session).ask(None, None, lambda: None)
    assert engine.queries == []


def test_an_error_is_not_asked_again(tmp_path):
    session, engine = make_session(tmp_path), HeldEngine()
    areas = QuickAreas(session)
    areas.ask(engine, None, lambda: None)
    engine.callbacks[0]({"error": "broken"})
    areas.ask(engine, None, lambda: None)
    assert len(engine.queries) == 1 and areas.shown() is None
