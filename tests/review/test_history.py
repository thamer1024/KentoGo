"""Tests for kentogo.review.history, with answers saved through kentogo.answers."""

from datetime import datetime, timezone

from kentogo.answers import save_answer, saved_problems
from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import Problem
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import QuizSession
from kentogo.review.history import AnswerHistory
from kentogo.review.record import LOSS_FROM_KATAGO, LOSS_FROM_SGF, LOSS_UNKNOWN
from kentogo.review.store import ReviewStore

WHEN = datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc)

PROBLEM = Problem(
    problem_id="p1",
    sgf_path="game.sgf",
    move_number=3,
    position=Position(19, 6.5, "japanese", (), (Move.from_gtp("Q16", "B"), Move.from_gtp("D4", "W")), "B"),
    actual_move=Move.from_gtp("A19", "B"),
    best_move=Move.from_gtp("Q4", "B"),
    points_lost=8.0,
)


def answered(gtp: str) -> QuizSession:
    """Start a session and answer it."""
    session = QuizSession(PROBLEM, ScoringPolicy())
    session.answer(Move.from_gtp(gtp, "B"))
    return session


def history() -> AnswerHistory:
    """Make a history in memory, with a fixed time."""
    return AnswerHistory(ReviewStore(":memory:"), now=lambda: WHEN)


def test_answer_judged_at_once():
    """An answer whose loss is in the SGF file is saved with its result."""
    answers = history()
    save_answer(answers, answered("Q4"))
    [record] = answers.previous("p1")
    assert (record.answer, record.correct, record.loss_source) == ("Q4", True, LOSS_FROM_SGF)
    assert record.answered_at == "2026-10-20T12:30:00+00:00"


def test_answer_judged_by_katago():
    """An answer judged by KataGo is saved with KataGo's losses and the number of visits."""
    answers = history()
    session = answered("R4")
    session.apply_evaluation(answer_loss=1.0, actual_loss=9.0)
    save_answer(answers, session, max_visits=500)
    [record] = answers.previous("p1")
    assert (record.answer_loss, record.actual_loss, record.correct) == (1.0, 9.0, True)
    assert (record.loss_source, record.max_visits) == (LOSS_FROM_KATAGO, 500)


def test_answer_that_cannot_be_judged():
    """An answer that cannot be judged (no KataGo) is saved without losses."""
    answers = history()
    save_answer(answers, answered("R4"))
    [record] = answers.previous("p1")
    assert (record.answer, record.answer_loss, record.correct, record.loss_source) == ("R4", None, None, LOSS_UNKNOWN)


def test_errors_do_not_stop_the_quiz():
    """When the database cannot be used, nothing is saved, and the error is kept."""
    answers = history()
    answers.store.close()
    save_answer(answers, answered("Q4"))
    assert answers.previous("p1") == []
    assert answers.all_previous() == {}
    assert answers.last_error


def test_saved_problems():
    """The problem of a saved answer can be read back, also without its SGF file."""
    answers = history()
    save_answer(answers, answered("Q4"))
    assert saved_problems(answers, ["p1", "missing"]) == [PROBLEM]
