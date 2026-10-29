"""Tests for kentogo.answers (records and problem copies between the quiz and the history)."""

from datetime import datetime, timedelta, timezone

import pytest

from kentogo.answers import record_of
from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import Problem
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import QuizSession
from kentogo.quiz.transform import BoardTransform
from kentogo.review.record import LOSS_FROM_COMPARE, LOSS_FROM_KATAGO, LOSS_FROM_SGF, LOSS_UNKNOWN

JST = timezone(timedelta(hours=9))
WHEN = datetime(2026, 10, 20, 21, 30, tzinfo=JST)

# Black to play. The game move A19 lost 8 points, and the best move is Q4.
PROBLEM = Problem(
    problem_id="p1",
    sgf_path="/games/game.sgf",
    move_number=3,
    position=Position(19, 6.5, "japanese", (), (Move.from_gtp("Q16", "B"), Move.from_gtp("D4", "W")), "B"),
    actual_move=Move.from_gtp("A19", "B"),
    best_move=Move.from_gtp("Q4", "B"),
    points_lost=8.0,
)


def answered(gtp: str, transform: BoardTransform = BoardTransform()) -> QuizSession:
    """Start a session and answer with a point given in the original direction."""
    session = QuizSession(PROBLEM, ScoringPolicy(), transform)
    session.answer(transform.move(Move.from_gtp(gtp, "B"), 19))
    return session


def test_record_of_a_move_from_the_sgf_file():
    """The best move is judged at once, with the losses from the SGF file."""
    record = record_of(answered("Q4"), WHEN)
    assert (record.problem_id, record.answered_at) == ("p1", "2026-10-20T21:30:00+09:00")
    assert (record.color, record.answer, record.actual_move, record.best_move) == ("B", "Q4", "A19", "Q4")
    assert (record.answer_loss, record.actual_loss, record.correct) == (0.0, 8.0, True)
    assert (record.loss_source, record.max_visits) == (LOSS_FROM_SGF, None)


def test_record_of_an_answer_not_judged_yet():
    """Another move has no losses and no judgment until KataGo has calculated them."""
    record = record_of(answered("R4"), WHEN)
    assert (record.answer_loss, record.actual_loss, record.correct) == (None, None, None)
    assert (record.loss_source, record.max_visits) == (LOSS_UNKNOWN, None)


def test_record_after_katago():
    """After KataGo's evaluation, both losses come from KataGo, with the number of visits."""
    session = answered("R4")
    session.apply_evaluation(answer_loss=1.0, actual_loss=9.0)
    record = record_of(session, WHEN, max_visits=500)
    assert (record.answer_loss, record.actual_loss, record.correct) == (1.0, 9.0, True)
    assert (record.loss_source, record.max_visits) == (LOSS_FROM_KATAGO, 500)


def test_record_keeps_the_original_direction_and_colors():
    """The answer is kept as it is on the original board, with the change that was used."""
    record = record_of(answered("Q4", BoardTransform(3, swap_colors=True)), WHEN)
    assert (record.color, record.answer) == ("B", "Q4")
    assert (record.symmetry, record.swap_colors) == (3, True)


def test_record_before_the_answer():
    """There is no record before the answer."""
    with pytest.raises(ValueError):
        record_of(QuizSession(PROBLEM, ScoringPolicy()), WHEN)


def test_record_of_the_comparison_model():
    """Losses calculated by the comparison model are marked as such."""
    session = answered("R4")
    session.apply_evaluation(answer_loss=1.0, actual_loss=9.0)
    assert record_of(session, WHEN, max_visits=500, comparison_model=True).loss_source == LOSS_FROM_COMPARE
