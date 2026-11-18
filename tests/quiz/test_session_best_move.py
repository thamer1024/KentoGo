"""Tests for QuizSession.best_move (the best move that is shown after the answer)."""

from test_session import BEST_LINE, PROBLEM, gtp

from kentogo.mistakes.problem import SOURCE_BEST_HUMAN
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import QuizSession


def answered() -> QuizSession:
    """Answer the test problem with its best move."""
    quiz = QuizSession(PROBLEM, ScoringPolicy())
    quiz.answer(gtp("Q4"))
    return quiz


def test_the_best_move_of_the_analysis_is_never_shown():
    """KataGo's best move of the game's analysis (the problem's best move) is not the best move that is shown."""
    quiz = answered()
    assert PROBLEM.best_move == gtp("Q4")
    assert quiz.best_move is None and not quiz.best_move_waiting  # Nothing is calculated: nothing is shown.
    quiz.expect(SOURCE_BEST_HUMAN)
    assert quiz.best_move is None and quiz.best_move_waiting  # Calculated: told so, nothing else.
    quiz.fail(SOURCE_BEST_HUMAN)
    assert quiz.best_move is None and not quiz.best_move_waiting


def test_the_best_move_is_the_first_move_of_the_sequence_from_the_problem_position():
    """It is the first move of the human-like sequence, which is not KataGo's best move of the analysis."""
    quiz = answered()
    quiz.expect(SOURCE_BEST_HUMAN)
    quiz.add_sequence(BEST_LINE[0], BEST_LINE[1:], SOURCE_BEST_HUMAN)
    assert quiz.best_move == gtp("R4") != PROBLEM.best_move and not quiz.best_move_waiting
