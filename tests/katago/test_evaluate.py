"""Tests for kentogo.katago.evaluate, with a fake engine."""

import pytest
from fake_analysis import FakeEngine

from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import Evaluation, EvaluationSettings, evaluate_moves, predict_after, predict_best

POSITION = Position(19, 6.5, "japanese", (), (Move.from_gtp("Q16", "B"), Move.from_gtp("D4", "W")), "B")
ANSWER = Move.from_gtp("Q4", "B")
ACTUAL = Move.from_gtp("A19", "B")


class Results:
    """Keeps what on_done and on_error were called with."""

    def __init__(self):
        """Start with nothing."""
        self.done: list[Evaluation] = []
        self.errors: list[str] = []


def start(settings=EvaluationSettings(max_visits=100, wide_root_noise=0.04)):
    """Start an evaluation with a fake engine, and return the engine and the results."""
    engine, results = FakeEngine(), Results()
    evaluate_moves(engine, POSITION, ANSWER, ACTUAL, settings, results.done.append, results.errors.append)
    return engine, results


def test_three_positions_are_analyzed():
    """The position before the moves, after the answer, and after the game move are analyzed."""
    engine, _ = start()
    moves = [request["moves"][2:] for request, _ in engine.queries]
    assert moves == [[], [["B", "Q4"]], [["B", "A19"]]]
    assert all(request["maxVisits"] == 100 for request, _ in engine.queries)
    assert all(request["overrideSettings"]["wideRootNoise"] == 0.04 for request, _ in engine.queries)


def test_losses_in_any_order():
    """The losses are calculated when all three answers are here, in any order."""
    engine, results = start()
    engine.answer(2, score=-6.0, pv=("R17", "Q17"))  # After the game move: black is 6 behind.
    engine.answer(0, score=2.0, pv=("R4", "D16"), best_score=1.75)  # Before the moves: black is 2 ahead.
    assert results.done == []
    engine.answer(1, score=1.5, pv=("D16", "C17"))  # After the answer: black is 1.5 ahead.
    assert len(results.done) == 1
    evaluation = results.done[0]
    assert (evaluation.answer_loss, evaluation.actual_loss) == (pytest.approx(0.5), pytest.approx(8.0))
    assert evaluation.answer_sequence == (Move.from_gtp("D16", "W"), Move.from_gtp("C17", "B"))
    assert evaluation.actual_sequence == (Move.from_gtp("R17", "W"), Move.from_gtp("Q17", "B"))
    # The best sequence in the problem position starts with the player to move.
    assert evaluation.best_sequence == (Move.from_gtp("R4", "B"), Move.from_gtp("D16", "W"))
    assert evaluation.best_loss == pytest.approx(0.25)  # The score after the best move is 1.75.
    assert results.errors == []


def test_error_is_reported_once():
    """If one analysis fails, on_error is called once and on_done is not called."""
    engine, results = start()
    engine.answer(0, score=2.0)
    engine.answer(1, error="KataGo stopped")
    engine.answer(2, error="KataGo stopped")
    assert results.done == []
    assert len(results.errors) == 1
    assert "KataGo stopped" in results.errors[0]


def test_predict_after_one_move():
    """One position is analyzed, and KataGo's sequence after the move is returned as moves."""
    engine, sequences, errors = FakeEngine(), [], []
    settings = EvaluationSettings(max_visits=100)
    predict_after(engine, POSITION, ACTUAL, settings, sequences.append, errors.append)
    assert len(engine.queries) == 1
    assert engine.queries[0][0]["moves"][2:] == [["B", "A19"]]
    engine.answer(0, score=-6.0, pv=("R17",))
    assert sequences == [(Move.from_gtp("R17", "W"),)]
    assert errors == []


def test_predict_after_error():
    """An error answer is passed to on_error."""
    engine, sequences, errors = FakeEngine(), [], []
    predict_after(engine, POSITION, ACTUAL, EvaluationSettings(), sequences.append, errors.append)
    engine.answer(0, error="KataGo stopped")
    assert sequences == []
    assert "KataGo stopped" in errors[0]


def test_predict_best_in_a_position():
    """The position itself is analyzed, and the best sequence starts with the move of the player to play."""
    engine, sequences, errors = FakeEngine(), [], []
    predict_best(engine, POSITION, EvaluationSettings(max_visits=100), sequences.append, errors.append)
    assert len(engine.queries) == 1 and engine.queries[0][0]["moves"][2:] == []
    engine.answer(0, score=1.0, pv=("C3", "R17"))
    assert sequences == [(Move.from_gtp("C3", "B"), Move.from_gtp("R17", "W"))] and errors == []
