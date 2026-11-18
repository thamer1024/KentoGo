"""Tests for kentogo.quiz.best_move_value (what KataGo finds that the best move does, after the answer)."""

from test_standings import make_session

from kentogo.common.types import Move
from kentogo.katago.evaluate import EvaluationSettings
from kentogo.mistakes.problem import SOURCE_BEST_HUMAN
from kentogo.quiz.best_move_value import BestMoveValue

SETTINGS = EvaluationSettings(estimate_visits=60, wide_root_noise=0.04)


class Engine:
    """Keeps the queries, so that a test answers them."""

    def __init__(self):
        self.queries, self.callbacks = [], []

    def query(self, request, callback):
        self.queries.append(request)
        self.callbacks.append(callback)
        return str(len(self.queries))


def answer(engine: Engine, index: int, lead: float, owner: float) -> None:
    engine.callbacks[index]({"rootInfo": {"scoreLead": lead}, "ownership": [owner] * 81})


def session_with_best_move(tmp_path):
    """Answer the problem, with the sequence from the problem position made (its first move is E5)."""
    session = make_session(tmp_path)
    session.add_sequence(Move.from_gtp("E5", "B"), (Move.from_gtp("D4", "W"),), SOURCE_BEST_HUMAN)
    return session


def test_the_best_move_is_read_once_after_the_answer(tmp_path):
    """After the answer, the position after the best move and after a pass are read once, with estimate_visits."""
    session, engine, changes = session_with_best_move(tmp_path), Engine(), []
    value = BestMoveValue(session)
    assert not value.running
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    assert value.running  # Asked, not come.
    assert len(engine.queries) == 2 and engine.queries[0]["maxVisits"] == 60
    assert engine.queries[0]["moves"][-1] == ["B", "E5"] and engine.queries[1]["moves"][-1] == ["B", "pass"]
    answer(engine, 0, 3.0, 0.0)
    answer(engine, 1, 1.0, 0.0)
    assert changes == [1] and value.value.points == 2.0 and not value.running


def test_nothing_is_read_until_the_best_move_is_known(tmp_path):
    """While the best move is being calculated (or when there is none), nothing is read; it is asked when it comes."""
    session, engine = make_session(tmp_path), Engine()
    session.expect(SOURCE_BEST_HUMAN)
    value = BestMoveValue(session)
    value.ask(engine, SETTINGS, lambda: None)
    assert engine.queries == [] and not value.running
    session.add_sequence(Move.from_gtp("E5", "B"), (Move.from_gtp("D4", "W"),), SOURCE_BEST_HUMAN)
    value.ask(engine, SETTINGS, lambda: None)
    assert len(engine.queries) == 2


def test_a_failed_reading_is_told_and_is_not_running(tmp_path):
    """When KataGo cannot read it, the screen is told (to stop saying that KataGo is reading)."""
    session, engine, changes = session_with_best_move(tmp_path), Engine(), []
    value = BestMoveValue(session)
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    engine.callbacks[0]({"error": "KataGo stopped"})
    assert changes == [1] and value.value is None and not value.running


def test_nothing_is_kept_after_the_problem_is_left(tmp_path):
    session, engine, changes = session_with_best_move(tmp_path), Engine(), []
    value = BestMoveValue(session)
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    value.stop()
    answer(engine, 0, 3.0, 0.0)
    answer(engine, 1, 1.0, 0.0)
    assert changes == [] and value.value is None


def test_nothing_is_read_without_katago(tmp_path):
    value = BestMoveValue(session_with_best_move(tmp_path))
    value.ask(None, SETTINGS, lambda: None)
    assert value.value is None
