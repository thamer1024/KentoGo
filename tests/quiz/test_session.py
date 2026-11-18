"""Tests for kentogo.quiz.session."""

from dataclasses import replace

import pytest

from kentogo.common.board import IllegalMoveError
from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import (
    SOURCE_BEST_HUMAN,
    SOURCE_GAME,
    SOURCE_RANK_ANSWER,
    Problem,
    Variation,
)
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import ANSWERED, ASKING, FAILED, WAITING, QuizSession
from kentogo.quiz.transform import BoardTransform


def gtp(point: str, color: str = "B") -> Move:
    """Make a move from GTP coordinates."""
    return Move.from_gtp(point, color)


# Black to play. The game move A19 lost 8 points, and the best move is Q4.
PROBLEM = Problem(
    problem_id="p1",
    sgf_path="game.sgf",
    move_number=3,
    position=Position(19, 6.5, "japanese", (), (gtp("Q16"), gtp("D4", "W")), "B"),
    actual_move=gtp("A19"),
    best_move=gtp("Q4"),
    points_lost=8.0,
    variations=(
        Variation((gtp("Q4"), gtp("D16", "W"), gtp("C17")), "katrain"),
        Variation((gtp("R4"), gtp("D16", "W")), "katago"),
    ),
    notes="Q4 is bigger",
)


# The sequence after the answer Q4, and the sequence from the problem position.
RANK_LINE = (gtp("Q4"), gtp("D16", "W"), gtp("C17"))
BEST_LINE = (gtp("R4"), gtp("D16", "W"))


def session(transform: BoardTransform = BoardTransform()) -> QuizSession:
    """Start a session with the test problem."""
    return QuizSession(PROBLEM, ScoringPolicy(), transform)


def test_best_move_is_correct():
    """The best move is known to lose 0 points, so it is judged at once."""
    quiz = session()
    result = quiz.answer(gtp("Q4"))
    assert quiz.phase == ANSWERED
    assert (result.answer_loss, result.correct) == (0.0, True)
    assert result.comparison.recovered_ratio == 1.0


def test_game_move_is_wrong():
    """The game move is known to lose 8 points, so it is judged at once."""
    result = session().answer(gtp("A19"))
    assert (result.answer_loss, result.correct) == (8.0, False)


def test_other_move_waits_for_katago():
    """For another move, the result is not judged until KataGo's losses are given."""
    quiz = session()
    result = quiz.answer(gtp("R4"))
    assert (result.answer_loss, result.comparison, result.correct) == (None, None, None)

    result = quiz.apply_evaluation(answer_loss=1.0, actual_loss=9.0)
    assert result.correct is True
    assert result.comparison.actual_loss == 9.0  # KataGo's value, not the one from the SGF file.


def test_wrong_answers():
    """A move with the wrong color, on a stone, or a second answer is not accepted."""
    quiz = session()
    with pytest.raises(IllegalMoveError):
        quiz.answer(gtp("R4", "W"))
    with pytest.raises(IllegalMoveError):
        quiz.answer(gtp("Q16"))
    assert quiz.phase == ASKING
    quiz.answer(gtp("Q4"))
    with pytest.raises(RuntimeError):
        quiz.answer(gtp("R4"))


def test_apply_evaluation_before_answer():
    """KataGo's losses cannot be given before the answer."""
    with pytest.raises(RuntimeError):
        session().apply_evaluation(1.0, 8.0)


def test_changed_problem_is_shown_before_and_after_the_answer():
    """The changed problem is shown while asking and after the answer, but the result uses the original."""
    transform = BoardTransform(1, swap_colors=True)
    quiz = session(transform)
    shown = quiz.shown_problem
    assert shown.position == transform.position(PROBLEM.position)
    assert shown.position.next_color == "W"
    assert quiz.shown_result is None

    shown_answer = transform.move(gtp("Q4"), 19)
    result = quiz.answer(shown_answer)
    assert result.answer == gtp("Q4")  # Changed back to the original.
    assert result.correct is True
    assert quiz.shown_problem.position == shown.position  # The board does not change.
    assert quiz.shown_problem.best_move == shown_answer
    assert quiz.shown_result.answer == shown_answer
    assert quiz.shown_move(gtp("Q4")) == shown_answer


def test_shown_notes_are_rewritten():
    """The notes are rewritten for the shown board. Without a change they stay the same."""
    flip = BoardTransform(4)
    assert session(flip).shown_problem.notes == "D4 is bigger"
    assert session().shown_problem.notes == "Q4 is bigger"


def test_shown_ai_comment_is_rewritten():
    """The AI commentary is rewritten for the shown board, in the same way as the notes."""
    quiz = QuizSession(replace(PROBLEM, ai_comment="Q4 is urgent"), ScoringPolicy(), BoardTransform(4))
    assert quiz.shown_problem.ai_comment == "D4 is urgent"


def test_shown_sequence_is_changed():
    """The sequence is shown on the changed board."""
    transform = BoardTransform(2)
    quiz = session(transform)
    quiz.answer(transform.move(gtp("Q4"), 19))
    quiz.add_sequence(RANK_LINE[0], RANK_LINE[1:], SOURCE_RANK_ANSWER)
    quiz.step_forward()
    quiz.step_forward()
    assert quiz.shown_sequence() == transform.moves(RANK_LINE[:2], 19)


def test_notes_are_shown_only_after_the_answer():
    """The notes are hidden while asking."""
    quiz = session()
    assert not quiz.notes_visible
    quiz.answer(gtp("Q4"))
    assert quiz.notes_visible


def test_replay_sequence():
    """After the answer, the sequence is shown one move at a time, forward and back."""
    quiz = session()
    assert quiz.shown_sequence() == ()
    quiz.step_forward()
    assert quiz.replay_step == 0  # Nothing is shown before the answer.

    quiz.answer(gtp("Q4"))
    quiz.add_sequence(RANK_LINE[0], RANK_LINE[1:], SOURCE_RANK_ANSWER)
    for _ in range(5):
        quiz.step_forward()
    assert quiz.shown_sequence() == RANK_LINE  # It stops at the end.
    quiz.step_back()
    assert quiz.shown_sequence() == RANK_LINE[:2]


def sources(quiz: QuizSession) -> list[tuple[str, str]]:
    """Return (source, status) of each sequence in the order of Tab."""
    return [(choice.source, choice.status) for choice in quiz.choices]


def two_sequences() -> QuizSession:
    """Answer Q4, with the sequence after the answer and the sequence from the problem position added."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.add_sequence(RANK_LINE[0], RANK_LINE[1:], SOURCE_RANK_ANSWER)
    quiz.add_sequence(BEST_LINE[0], BEST_LINE[1:], SOURCE_BEST_HUMAN)
    return quiz


def test_katago_sequences_are_in_a_fixed_order():
    """Tab order: the sequence after the answer, the game's own moves, and the sequence from the problem position."""
    quiz = QuizSession(replace(PROBLEM, game_line=(gtp("A19"), gtp("B18", "W"))), ScoringPolicy())
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_BEST_HUMAN)
    quiz.expect(SOURCE_RANK_ANSWER)
    assert sources(quiz) == [(SOURCE_RANK_ANSWER, WAITING), (SOURCE_GAME, ""), (SOURCE_BEST_HUMAN, WAITING)]
    # The first sequence is shown first, while KataGo is still calculating it.
    assert quiz.variation_index == 0 and quiz.variation is None and quiz.shown_sequence() == ()
    quiz.apply_evaluation(1.0, 9.0)
    quiz.add_sequence(gtp("R4"), (gtp("C3", "W"), gtp("D3")), SOURCE_RANK_ANSWER)
    assert quiz.choices[0].variation == Variation((gtp("R4"), gtp("C3", "W"), gtp("D3")), SOURCE_RANK_ANSWER)
    assert quiz.variation_index == 0 and quiz.replay_step == 0


def test_without_katago_there_is_no_sequence():
    """When KataGo calculates nothing (and the game has no moves after the game move), no sequence is shown."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    assert quiz.choices == () and quiz.variation is None and quiz.choice is None


def test_shown_sequence_stays_when_another_arrives():
    """A sequence that arrives later does not change which one is shown."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_BEST_HUMAN)
    quiz.expect(SOURCE_RANK_ANSWER)
    quiz.next_variation()  # The sequence from the problem position.
    quiz.add_sequence(gtp("R4"), (gtp("R3", "W"),), SOURCE_RANK_ANSWER)
    quiz.add_sequence(BEST_LINE[0], BEST_LINE[1:], SOURCE_BEST_HUMAN)
    assert quiz.variation == Variation(BEST_LINE, SOURCE_BEST_HUMAN)
    quiz.select_variation(0)
    assert quiz.variation == Variation((gtp("R4"), gtp("R3", "W")), SOURCE_RANK_ANSWER)


def test_failed_sequence_is_marked():
    """A sequence that KataGo could not calculate stays in the order, marked as failed."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_RANK_ANSWER)
    quiz.fail(SOURCE_RANK_ANSWER)
    assert sources(quiz)[0] == (SOURCE_RANK_ANSWER, FAILED)
    quiz.fail(SOURCE_BEST_HUMAN)  # Not expected, so nothing is added.
    assert len(quiz.choices) == 1


def test_next_variation_goes_around():
    """next_variation goes through all sequences and back to the first one."""
    quiz = two_sequences()
    quiz.step_forward()
    quiz.next_variation()
    assert (quiz.variation_index, quiz.replay_step) == (1, 1)  # Its first move is shown at once.
    quiz.next_variation()
    assert quiz.variation_index == 0


def test_previous_variation_goes_around_the_other_way():
    """previous_variation goes back through the sequences, from the first one to the last one."""
    quiz = two_sequences()
    quiz.previous_variation()
    assert (quiz.variation_index, quiz.replay_step) == (1, 1)  # From the first to the last of two.
    quiz.previous_variation()
    assert quiz.variation_index == 0


def test_select_another_sequence():
    """Choosing another sequence shows its first move at once; a sequence still calculated starts empty."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.add_sequence(BEST_LINE[0], BEST_LINE[1:], SOURCE_BEST_HUMAN)
    quiz.expect(SOURCE_RANK_ANSWER)
    quiz.select_variation(1)
    assert quiz.replay_step == 1 and quiz.shown_sequence() == (gtp("R4"),)
    quiz.step_back()
    assert quiz.shown_sequence() == ()
    with pytest.raises(IndexError):
        quiz.select_variation(2)
    quiz.select_variation(0)
    assert quiz.variation is None and quiz.replay_step == 0


def test_candidate_move_from_analysis_data_is_judged_at_once():
    """A move in KaTrain's analysis data is judged without KataGo."""
    problem = replace(PROBLEM, candidate_losses=(("R4", 1.0), ("Q4", 0.0)))
    quiz = QuizSession(problem, ScoringPolicy())
    result = quiz.answer(gtp("R4"))
    assert (result.answer_loss, result.correct) == (1.0, True)
    other = QuizSession(problem, ScoringPolicy()).answer(gtp("K10"))
    assert other.correct is None  # Not in the analysis data: KataGo is needed.


def test_the_loss_of_the_shown_sequences_first_move():
    """While another sequence is shown, its first move and its loss are given; for the answer's own, nothing."""
    problem = replace(PROBLEM, candidate_losses=(("R4", 1.0),))
    quiz = QuizSession(problem, ScoringPolicy())
    quiz.answer(gtp("A19"))  # The game move: judged at once.
    quiz.add_sequence(gtp("Q4"), (gtp("D16", "W"),), SOURCE_BEST_HUMAN)
    assert quiz.choice.source == SOURCE_BEST_HUMAN and quiz.sequence_loss() == (gtp("Q4"), 0.0)  # The best move.
    quiz.add_sequence(gtp("R4"), (gtp("D16", "W"),), SOURCE_BEST_HUMAN)
    assert quiz.sequence_loss() == (gtp("R4"), 1.0)  # From KaTrain's analysis data.
    other = two_sequences()
    assert other.sequence_loss() is None  # The shown sequence starts with the answer.
    other.next_variation()
    assert other.sequence_loss() == (gtp("R4"), None)  # Not known.


def test_the_end_of_a_sequence_is_where_the_territory_can_be_shown():
    """Only at the last move of a sequence."""
    quiz = QuizSession(PROBLEM, ScoringPolicy())
    quiz.answer(gtp("Q4"))
    quiz.add_sequence(gtp("Q4"), (gtp("B18", "W"),), SOURCE_RANK_ANSWER)
    quiz.select_variation(0)  # Its first move is shown.
    assert quiz.choice.source == SOURCE_RANK_ANSWER and quiz.sequence_at_end() is None
    quiz.step_forward()
    assert quiz.sequence_at_end() == quiz.choice.variation


def test_the_verdict_goes_with_the_answers_sequence():
    """Correct or wrong is shown with the answer's sequence only; without it, with the first sequence."""
    game_line = (gtp("A19"), gtp("B18", "W"))
    quiz = QuizSession(replace(PROBLEM, game_line=game_line), ScoringPolicy())
    quiz.answer(gtp("Q4"))
    assert [choice.source for choice in quiz.choices] == [SOURCE_GAME] and quiz.shows_verdict  # No KataGo.
    quiz.add_sequence(gtp("Q4"), (gtp("K11", "W"),), SOURCE_RANK_ANSWER)
    quiz.add_sequence(gtp("Q4"), (gtp("K12", "W"),), SOURCE_BEST_HUMAN)
    sources = [choice.source for choice in quiz.choices]
    quiz.select_variation(sources.index(SOURCE_RANK_ANSWER))
    assert quiz.shows_verdict
    for source in (SOURCE_GAME, SOURCE_BEST_HUMAN):
        quiz.select_variation(sources.index(source))
        assert not quiz.shows_verdict


def test_the_games_own_moves_come_after_the_answers_sequence():
    """Tab order: the sequence after the answer, the game's own moves, then the sequence from the position."""
    game_line = (gtp("A19"), gtp("B18", "W"), gtp("C17"))
    quiz = QuizSession(replace(PROBLEM, game_line=game_line), ScoringPolicy())
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_BEST_HUMAN)
    quiz.expect(SOURCE_RANK_ANSWER)
    assert [choice.source for choice in quiz.choices] == [SOURCE_RANK_ANSWER, SOURCE_GAME, SOURCE_BEST_HUMAN]
    assert quiz.choices[1].variation == Variation(game_line, SOURCE_GAME)
