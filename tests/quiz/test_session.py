"""Tests for kentogo.quiz.session."""

from dataclasses import replace

import pytest

from kentogo.common.board import IllegalMoveError
from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import (
    SOURCE_KATAGO_ACTUAL,
    SOURCE_KATAGO_ANSWER,
    SOURCE_KATAGO_COMPARE,
    Problem,
    Variation,
)
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import ANSWERED, ASKING, FAILED, OFFERED, WAITING, QuizSession
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
    quiz.step_forward()
    quiz.step_forward()
    assert quiz.shown_sequence() == transform.moves(PROBLEM.variations[0].moves[:2], 19)


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
    for _ in range(5):
        quiz.step_forward()
    assert quiz.shown_sequence() == PROBLEM.variations[0].moves  # It stops at the end.
    quiz.step_back()
    assert quiz.shown_sequence() == PROBLEM.variations[0].moves[:2]


def sources(quiz: QuizSession) -> list[tuple[str, str]]:
    """Return (source, status) of each sequence in the order of Tab."""
    return [(choice.source, choice.status) for choice in quiz.choices]


def test_katago_sequences_are_in_a_fixed_order():
    """Tab order: after the answer, the SGF file's sequences, after the game move, and last the comparison model."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_KATAGO_ANSWER)
    quiz.expect(SOURCE_KATAGO_ACTUAL)
    quiz.expect(SOURCE_KATAGO_COMPARE)
    assert sources(quiz) == [
        ("katago", WAITING),
        ("katrain", ""),
        ("katago", ""),  # The SGF file's own second sequence.
        (SOURCE_KATAGO_ACTUAL, WAITING),
        (SOURCE_KATAGO_COMPARE, WAITING),
    ]
    # The sequence after the answer is shown first, while KataGo is still calculating it.
    assert quiz.variation_index == 0 and quiz.variation is None and quiz.shown_sequence() == ()
    quiz.apply_evaluation(1.0, 9.0, (gtp("C3", "W"), gtp("D3")), actual_sequence=(gtp("B18", "W"),))
    assert quiz.variation == Variation((gtp("R4"), gtp("C3", "W"), gtp("D3")), "katago")
    assert quiz.choices[3].variation == Variation((gtp("A19"), gtp("B18", "W")), SOURCE_KATAGO_ACTUAL)
    assert quiz.choices[4].status == WAITING  # The comparison model is still calculating.
    assert quiz.replay_step == 0


def test_without_katago_the_sgf_sequence_is_first():
    """When KataGo calculates nothing, the SGF file's sequence is shown first."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    assert quiz.variation == PROBLEM.variations[0]
    assert len(quiz.choices) == 2


def test_shown_sequence_stays_when_another_arrives():
    """A sequence that arrives later does not change which one is shown."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_KATAGO_ANSWER)
    quiz.expect(SOURCE_KATAGO_COMPARE)
    quiz.next_variation()  # KaTrain's sequence.
    quiz.add_sequence(gtp("Q3"), (gtp("R3", "W"),), SOURCE_KATAGO_COMPARE)
    quiz.add_sequence(gtp("R4"), (gtp("C3", "W"),), SOURCE_KATAGO_ANSWER)
    assert quiz.variation == PROBLEM.variations[0]
    quiz.next_variation()
    quiz.next_variation()
    assert quiz.variation == Variation((gtp("Q3"), gtp("R3", "W")), SOURCE_KATAGO_COMPARE)


def test_offered_sequence_waits_until_it_is_asked_for():
    """An offered sequence is in the order without moves, and becomes waiting when KataGo is asked."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.offer(SOURCE_KATAGO_COMPARE)
    assert sources(quiz)[-1] == (SOURCE_KATAGO_COMPARE, OFFERED)
    quiz.expect(SOURCE_KATAGO_COMPARE)
    assert sources(quiz)[-1] == (SOURCE_KATAGO_COMPARE, WAITING)
    quiz.offer(SOURCE_KATAGO_COMPARE)  # Offering again does not undo the asking.
    assert sources(quiz)[-1] == (SOURCE_KATAGO_COMPARE, WAITING)


def test_failed_sequence_is_marked():
    """A sequence that KataGo could not calculate stays in the order, marked as failed."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_KATAGO_COMPARE)
    quiz.fail(SOURCE_KATAGO_COMPARE)
    assert sources(quiz)[-1] == (SOURCE_KATAGO_COMPARE, FAILED)
    quiz.fail(SOURCE_KATAGO_ANSWER)  # Not expected, so nothing is added.
    assert len(quiz.choices) == 3


def test_no_sequence_after_the_game_move_when_it_is_the_answer():
    """When the answer is the game move, its sequence is the one after the answer, and is not added twice."""
    quiz = session()
    quiz.answer(gtp("A19"))
    quiz.expect(SOURCE_KATAGO_ANSWER)
    quiz.expect(SOURCE_KATAGO_ACTUAL)
    quiz.add_sequence(gtp("A19"), (gtp("B18", "W"),), SOURCE_KATAGO_ACTUAL)
    quiz.add_sequence(gtp("A19"), (gtp("B18", "W"),), SOURCE_KATAGO_ANSWER)
    assert [choice.source for choice in quiz.choices] == ["katago", "katrain", "katago"]
    assert quiz.variation == Variation((gtp("A19"), gtp("B18", "W")), SOURCE_KATAGO_ANSWER)


def test_comparison_result_is_shown_with_its_sequence():
    """The comparison model's result is shown only while its sequence is shown."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.apply_evaluation(1.0, 8.0)
    quiz.expect(SOURCE_KATAGO_COMPARE)
    compare = quiz.apply_compare_evaluation(3.0, 6.0, (gtp("Q3"), gtp("R3", "W")), 0.2)
    assert (compare.answer_loss, compare.correct) == (3.0, False)  # It recovers only half of the loss.
    assert (quiz.compare_best, quiz.compare_best_loss) == (gtp("Q3"), 0.2)
    assert quiz.displayed_result.answer_loss == 1.0  # KaTrain's sequence is shown first.
    quiz.select_variation(2)  # katrain, katago (in the SGF file), then the comparison model.
    assert quiz.showing_compare and quiz.displayed_result.answer_loss == 3.0
    quiz.next_variation()
    assert not quiz.showing_compare and quiz.displayed_result.answer_loss == 1.0


def test_comparison_without_a_sequence_is_marked_as_failed():
    """Without a best sequence, the comparison model's sequence is marked as failed."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_KATAGO_COMPARE)
    quiz.apply_compare_evaluation(3.0, 6.0, ())
    assert quiz.choices[-1].status == FAILED and quiz.compare_best is None


def test_next_variation_goes_around():
    """next_variation goes through all sequences and back to the first one."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.step_forward()
    quiz.next_variation()
    assert (quiz.variation_index, quiz.replay_step) == (1, 0)
    quiz.next_variation()
    assert quiz.variation_index == 0


def test_select_another_sequence():
    """Choosing another sequence shows it from the start."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.step_forward()
    quiz.select_variation(1)
    assert quiz.replay_step == 0
    quiz.step_forward()
    assert quiz.shown_sequence() == (gtp("R4"),)
    with pytest.raises(IndexError):
        quiz.select_variation(2)


def test_candidate_move_from_analysis_data_is_judged_at_once():
    """A move in KaTrain's analysis data is judged without KataGo."""
    problem = replace(PROBLEM, candidate_losses=(("R4", 1.0), ("Q4", 0.0)))
    quiz = QuizSession(problem, ScoringPolicy())
    result = quiz.answer(gtp("R4"))
    assert (result.answer_loss, result.correct) == (1.0, True)
    other = QuizSession(problem, ScoringPolicy()).answer(gtp("K10"))
    assert other.correct is None  # Not in the analysis data: KataGo is needed.


def test_sgf_losses_can_be_turned_off():
    """When another model judges, even the best move and the game move wait for KataGo."""
    quiz = QuizSession(PROBLEM, ScoringPolicy(), use_sgf_losses=False)
    assert quiz.answer(gtp("Q4")).correct is None
    assert QuizSession(PROBLEM, ScoringPolicy(), use_sgf_losses=False).known_loss(gtp("A19")) is None


def test_the_loss_of_the_shown_sequences_first_move():
    """While another sequence is shown, its first move and its loss are given; for the answer's own, nothing."""
    problem = replace(PROBLEM, candidate_losses=(("R4", 1.0),))
    quiz = QuizSession(problem, ScoringPolicy())
    quiz.answer(gtp("A19"))  # The game move: judged at once.
    assert quiz.choice.source == "katrain" and quiz.sequence_loss() == (gtp("Q4"), 0.0)  # The best move.
    quiz.next_variation()
    assert quiz.sequence_loss() == (gtp("R4"), 1.0)  # From KaTrain's analysis data.
    other = QuizSession(PROBLEM, ScoringPolicy())
    other.answer(gtp("Q4"))
    assert other.sequence_loss() is None  # The shown sequence starts with the answer.
    other.next_variation()
    assert other.sequence_loss() == (gtp("R4"), None)  # Not known.


def test_the_end_of_a_sequence_is_where_the_territory_can_be_shown():
    """Only at the last move of a sequence that is not the game's continuation."""
    quiz = QuizSession(PROBLEM, ScoringPolicy())
    quiz.answer(gtp("Q4"))
    assert quiz.sequence_at_end() is None  # The start of KaTrain's sequence.
    for _ in range(3):
        quiz.step_forward()
    assert quiz.sequence_at_end() == PROBLEM.variations[0]
    quiz.add_sequence(gtp("A19"), (gtp("B18", "W"),), SOURCE_KATAGO_ACTUAL)
    quiz.select_variation(len(quiz.choices) - 1)
    quiz.step_forward()
    quiz.step_forward()
    assert quiz.choice.source == SOURCE_KATAGO_ACTUAL and quiz.sequence_at_end() is None


def test_the_ai_commentary_is_not_shown_with_the_comparison_model():
    """The AI commentary goes with every sequence but the comparison model's (another AI's view)."""
    quiz = QuizSession(PROBLEM, ScoringPolicy())
    quiz.answer(gtp("Q4"))
    assert quiz.choice.source == "katrain" and quiz.shows_ai_comment
    quiz.add_sequence(gtp("A19"), (gtp("B18", "W"),), SOURCE_KATAGO_ACTUAL)
    quiz.add_sequence(gtp("K10"), (gtp("K11", "W"),), SOURCE_KATAGO_ANSWER)
    quiz.add_sequence(gtp("D4"), (gtp("D5", "W"),), SOURCE_KATAGO_COMPARE)
    sources = [choice.source for choice in quiz.choices]
    for source in (SOURCE_KATAGO_ANSWER, SOURCE_KATAGO_ACTUAL, "katrain"):
        quiz.select_variation(sources.index(source))
        assert quiz.shows_ai_comment
    quiz.select_variation(sources.index(SOURCE_KATAGO_COMPARE))
    assert not quiz.shows_ai_comment


def test_the_verdict_goes_with_the_answers_sequence():
    """Correct or wrong is shown with the answer's sequence only; without it, with the first sequence."""
    quiz = QuizSession(PROBLEM, ScoringPolicy())
    quiz.answer(gtp("Q4"))
    assert quiz.choice.source == "katrain" and quiz.shows_verdict  # No KataGo: the first sequence.
    quiz.add_sequence(gtp("A19"), (gtp("B18", "W"),), SOURCE_KATAGO_ACTUAL)
    sources = [choice.source for choice in quiz.choices]
    quiz.select_variation(sources.index(SOURCE_KATAGO_ACTUAL))
    assert not quiz.shows_verdict
    quiz.add_sequence(gtp("K10"), (gtp("K11", "W"),), SOURCE_KATAGO_ANSWER)
    sources = [choice.source for choice in quiz.choices]
    quiz.select_variation(sources.index(SOURCE_KATAGO_ANSWER))
    assert quiz.shows_verdict
    quiz.select_variation(sources.index("katrain"))
    assert not quiz.shows_verdict
