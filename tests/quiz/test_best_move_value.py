"""Tests for kentogo.quiz.best_move_value (what KataGo finds that the best move does, after the answer)."""

from test_standings import make_session

from kentogo.katago.evaluate import EvaluationSettings
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


def test_the_best_move_is_read_once_after_the_answer(tmp_path):
    """After the answer, the position after the best move and after a pass are read once, with estimate_visits."""
    session, engine, changes = make_session(tmp_path), Engine(), []
    value = BestMoveValue(session)
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    assert len(engine.queries) == 2 and engine.queries[0]["maxVisits"] == 60
    assert engine.queries[0]["moves"][-1] == ["B", "E5"] and engine.queries[1]["moves"][-1] == ["B", "pass"]
    answer(engine, 0, 3.0, 0.0)
    answer(engine, 1, 1.0, 0.0)
    assert changes == [1] and value.value.points == 2.0


def test_nothing_is_kept_after_the_problem_is_left(tmp_path):
    session, engine, changes = make_session(tmp_path), Engine(), []
    value = BestMoveValue(session)
    value.ask(engine, SETTINGS, lambda: changes.append(1))
    value.stop()
    answer(engine, 0, 3.0, 0.0)
    answer(engine, 1, 1.0, 0.0)
    assert changes == [] and value.value is None


def test_nothing_is_read_without_katago(tmp_path):
    value = BestMoveValue(make_session(tmp_path))
    value.ask(None, SETTINGS, lambda: None)
    assert value.value is None
