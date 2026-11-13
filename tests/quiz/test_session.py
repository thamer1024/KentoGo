"""Tests for kentogo.quiz.session."""

from dataclasses import replace

import pytest

from kentogo.common.board import IllegalMoveError
from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import (
    SOURCE_GAME,
    SOURCE_KATAGO_ANSWER,
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
    """Tab order: the replies of the opponent's rank, the strongest replies, and the SGF file's sequences."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_KATAGO_ANSWER)
    quiz.expect(SOURCE_RANK_ANSWER)
    assert sources(quiz) == [
        (SOURCE_RANK_ANSWER, WAITING),
        ("katago", WAITING),
        ("katrain", ""),
        ("katago", ""),  # The SGF file's own second sequence.
    ]
    # The first sequence is shown first, while KataGo is still calculating it.
    assert quiz.variation_index == 0 and quiz.variation is None and quiz.shown_sequence() == ()
    quiz.apply_evaluation(1.0, 9.0, (gtp("C3", "W"), gtp("D3")))
    assert quiz.choices[1].variation == Variation((gtp("R4"), gtp("C3", "W"), gtp("D3")), "katago")
    assert quiz.variation_index == 0 and quiz.variation is None and quiz.replay_step == 0


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
    quiz.expect(SOURCE_RANK_ANSWER)
    quiz.next_variation()
    quiz.next_variation()  # KaTrain's sequence.
    quiz.add_sequence(gtp("R4"), (gtp("R3", "W"),), SOURCE_RANK_ANSWER)
    quiz.add_sequence(gtp("R4"), (gtp("C3", "W"),), SOURCE_KATAGO_ANSWER)
    assert quiz.variation == PROBLEM.variations[0]
    quiz.select_variation(0)
    assert quiz.variation == Variation((gtp("R4"), gtp("R3", "W")), SOURCE_RANK_ANSWER)


def test_failed_sequence_is_marked():
    """A sequence that KataGo could not calculate stays in the order, marked as failed."""
    quiz = session()
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_RANK_ANSWER)
    quiz.fail(SOURCE_RANK_ANSWER)
    assert sources(quiz)[0] == (SOURCE_RANK_ANSWER, FAILED)
    quiz.fail(SOURCE_KATAGO_ANSWER)  # Not expected, so nothing is added.
    assert len(quiz.choices) == 3


def test_next_variation_goes_around():
    """next_variation goes through all sequences and back to the first one."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.step_forward()
    quiz.next_variation()
    assert (quiz.variation_index, quiz.replay_step) == (1, 1)  # Its first move is shown at once.
    quiz.next_variation()
    assert quiz.variation_index == 0


def test_previous_variation_goes_around_the_other_way():
    """previous_variation goes back through the sequences, from the first one to the last one."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.previous_variation()
    assert (quiz.variation_index, quiz.replay_step) == (1, 1)  # From the first to the last of two.
    quiz.previous_variation()
    assert quiz.variation_index == 0


def test_select_another_sequence():
    """Choosing another sequence shows its first move at once; a sequence still calculated starts empty."""
    quiz = session()
    quiz.answer(gtp("Q4"))
    quiz.step_forward()
    quiz.select_variation(1)
    assert quiz.replay_step == 1 and quiz.shown_sequence() == (gtp("R4"),)
    quiz.step_back()
    assert quiz.shown_sequence() == ()
    with pytest.raises(IndexError):
        quiz.select_variation(2)
    quiz.expect(SOURCE_RANK_ANSWER)
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
    assert quiz.choice.source == "katrain" and quiz.sequence_loss() == (gtp("Q4"), 0.0)  # The best move.
    quiz.next_variation()
    assert quiz.sequence_loss() == (gtp("R4"), 1.0)  # From KaTrain's analysis data.
    other = QuizSession(PROBLEM, ScoringPolicy())
    other.answer(gtp("Q4"))
    assert other.sequence_loss() is None  # The shown sequence starts with the answer.
    other.next_variation()
    assert other.sequence_loss() == (gtp("R4"), None)  # Not known.


def test_the_end_of_a_sequence_is_where_the_territory_can_be_shown():
    """Only at the last move of a sequence (KataGo's ones too)."""
    quiz = QuizSession(PROBLEM, ScoringPolicy())
    quiz.answer(gtp("Q4"))
    assert quiz.sequence_at_end() is None  # The start of KaTrain's sequence.
    for _ in range(3):
        quiz.step_forward()
    assert quiz.sequence_at_end() == PROBLEM.variations[0]
    quiz.add_sequence(gtp("Q4"), (gtp("B18", "W"),), SOURCE_RANK_ANSWER)
    quiz.select_variation(0)  # Its first move is shown.
    assert quiz.choice.source == SOURCE_RANK_ANSWER and quiz.sequence_at_end() is None
    quiz.step_forward()
    assert quiz.sequence_at_end() == quiz.choice.variation


def test_the_verdict_goes_with_the_answers_sequence():
    """Correct or wrong is shown with the answer's sequences only; without them, with the first sequence."""
    game_line = (gtp("A19"), gtp("B18", "W"))
    quiz = QuizSession(replace(PROBLEM, game_line=game_line), ScoringPolicy())
    quiz.answer(gtp("Q4"))
    sources = [choice.source for choice in quiz.choices]
    assert sources[0] == SOURCE_GAME and not quiz.shows_verdict  # No KataGo: not with the game's moves,
    quiz.select_variation(sources.index("katrain"))
    assert quiz.shows_verdict  # but with the first sequence after them.
    quiz.add_sequence(gtp("Q4"), (gtp("K11", "W"),), SOURCE_RANK_ANSWER)
    quiz.add_sequence(gtp("Q4"), (gtp("K12", "W"),), SOURCE_KATAGO_ANSWER)
    sources = [choice.source for choice in quiz.choices]
    for source in (SOURCE_RANK_ANSWER, SOURCE_KATAGO_ANSWER):
        quiz.select_variation(sources.index(source))
        assert quiz.shows_verdict
    quiz.select_variation(sources.index("katrain"))
    assert not quiz.shows_verdict


def test_the_games_own_moves_come_after_the_answers_sequence():
    """Tab order: the replies of the opponent's rank, the strongest replies, the game's own moves, then KaTrain's."""
    game_line = (gtp("A19"), gtp("B18", "W"), gtp("C17"))
    quiz = QuizSession(replace(PROBLEM, game_line=game_line), ScoringPolicy())
    quiz.answer(gtp("R4"))
    quiz.expect(SOURCE_KATAGO_ANSWER)
    quiz.expect(SOURCE_RANK_ANSWER)
    assert [choice.source for choice in quiz.choices][:4] == [
        SOURCE_RANK_ANSWER,
        SOURCE_KATAGO_ANSWER,
        SOURCE_GAME,
        "katrain",
    ]
    assert quiz.choices[2].variation == Variation(game_line, SOURCE_GAME)
