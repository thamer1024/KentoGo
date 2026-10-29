"""Tests for kentogo.quiz.quiz_run, with fake KataGo engines and a listener that keeps what it is told."""

from dataclasses import replace

import pytest
from fake_analysis import FakeEngine

from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import EvaluationSettings
from kentogo.mistakes.problem import (
    SOURCE_KATAGO_ACTUAL,
    SOURCE_KATAGO_ANSWER,
    SOURCE_KATAGO_COMPARE,
    Problem,
    Variation,
)
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.quiz_run import REASON_EVALUATING, REASON_FAILED, REASON_NO_ENGINE, Judging, QuizRun
from kentogo.quiz.session import ANSWERED, FAILED, OFFERED, WAITING
from kentogo.quiz.transform import BoardTransform

MAIN = EvaluationSettings(max_visits=100)
COMPARE = EvaluationSettings(max_visits=30)


def point(gtp: str) -> tuple[int, int]:
    """Return the point of GTP coordinates."""
    return Move.from_gtp(gtp, "B").coord


def problem(problem_id: str = "p1") -> Problem:
    """Black to play. The game move A19 lost 8 points, and the best move Q4 loses none."""
    moves = (Move.from_gtp("Q16", "B"), Move.from_gtp("D4", "W"))
    return Problem(
        problem_id=problem_id,
        sgf_path="game.sgf",
        move_number=3,
        position=Position(19, 6.5, "japanese", (), moves, "B"),
        actual_move=Move.from_gtp("A19", "B"),
        best_move=Move.from_gtp("Q4", "B"),
        points_lost=8.0,
        variations=(Variation((Move.from_gtp("Q4", "B"),), "katrain"),),
    )


class Listener:
    """Keeps what the quiz tells the screen."""

    def __init__(self):
        """Start with nothing told."""
        self.started_with: list = []
        self.changes: list = []
        self.failures: list[tuple[str, str]] = []

    def started(self, session):
        """Keep the session of the problem asked now (None at the end)."""
        self.started_with.append(session)

    def changed(self, session):
        """Keep the session that changed."""
        self.changes.append(session)

    def failed(self, text_key, reason):
        """Keep the error."""
        self.failures.append((text_key, reason))


class Saved:
    """Keeps the saved answers as (problem ID, correct, visits, by the comparison model)."""

    def __init__(self):
        """Start with nothing saved."""
        self.answers: list[tuple] = []

    def __call__(self, session, max_visits, by_compare):
        """Keep one saved answer."""
        self.answers.append((session.problem.problem_id, session.result.correct, max_visits, by_compare))


def make_run(problems=None, judging=None, **values):
    """Make a quiz with fake engines (a main one; a comparison one only if the judging has it) and start it."""
    listener, saved = Listener(), Saved()
    judging = judging if judging is not None else Judging(FakeEngine(), MAIN)
    run = QuizRun(
        problems if problems is not None else [problem()],
        ScoringPolicy(),
        BoardTransform,
        judging,
        listener,
        save=saved,
        **values,
    )
    run.start(0)
    return run, listener, saved


def judge(engine: FakeEngine, first: int, answer_score: float) -> None:
    """Answer the three analyses of a judging that start at the query `first`: black leads by 2 before the moves."""
    engine.answer(first, score=2.0, pv=("Q4",))
    engine.answer(first + 1, score=answer_score, pv=("D16",))
    engine.answer(first + 2, score=-6.0, pv=("R17",))


def test_the_problems_are_asked_one_after_another():
    """Each problem is told when it starts, and the end is told with None."""
    run, listener, _ = make_run([problem("p1"), problem("p2")])
    assert [s.problem.problem_id for s in listener.started_with] == ["p1"] and run.index == 0
    run.answer(point("Q4"))
    run.judging.engine.answer(0, score=1.0, pv=("D16",))
    run.judging.engine.answer(1, score=-6.0, pv=("R17",))
    assert run.next_problem()
    assert listener.started_with[-1].problem.problem_id == "p2"
    run.answer(point("A19"))
    run.judging.engine.answer(2, score=-6.0, pv=("R17",))
    assert run.next_problem() and listener.started_with[-1] is None and run.session is None
    assert not run.next_problem()  # After the end, nothing happens.


def test_an_answer_in_the_file_is_judged_at_once_and_saved():
    """The best move is judged from the file: it is saved once, and KataGo shows the sequences after it."""
    run, listener, saved = make_run()
    assert run.answer(point("Q4")) == ""
    session = run.session
    assert session.phase == ANSWERED and session.result.correct is True
    assert saved.answers == [("p1", True, None, False)]
    assert not run.busy and run.calculating  # The sequences are still being calculated.
    engine = run.judging.engine
    assert [request["moves"][-1] for request, _ in engine.queries] == [["B", "Q4"], ["B", "A19"]]
    engine.answer(0, score=1.0, pv=("D16",))
    engine.answer(1, error="KataGo stopped")
    statuses = {choice.source: choice.status for choice in session.choices}
    assert statuses[SOURCE_KATAGO_ACTUAL] == FAILED and statuses[SOURCE_KATAGO_ANSWER] != WAITING
    assert not run.calculating and listener.changes == [session, session]


def test_the_game_move_gets_one_sequence():
    """When the answer is the game move, KataGo is asked only for the sequence after it."""
    run, _, saved = make_run()
    run.answer(point("A19"))
    assert len(run.judging.engine.queries) == 1 and saved.answers == [("p1", False, None, False)]


def test_other_answers_are_judged_by_katago():
    """While KataGo judges, the quiz is busy and tells why; the losses are kept and the answer is saved then."""
    run, listener, saved = make_run()
    run.answer(point("R4"))
    session = run.session
    assert run.busy and run.calculating and not run.can_play()
    assert run.waiting_reason(session) == (REASON_EVALUATING, {})
    assert not run.next_problem() and not run.next_variation()
    assert saved.answers == []
    judge(run.judging.engine, 0, answer_score=1.5)  # The answer loses 0.5 points.
    assert not run.busy and run.can_play() and run.waiting_reason(session) is None
    assert session.result.correct is True and saved.answers == [("p1", True, 100, False)]
    assert listener.changes == [session]


def test_the_comparison_model_can_judge():
    """With the comparison model judging, even the best move is calculated by it, with its own visits."""
    main, compare = FakeEngine(), FakeEngine()
    run, _, saved = make_run(judging=Judging(main, MAIN, "", compare, COMPARE, judge_with_compare=True))
    run.answer(point("Q4"))
    assert main.queries == [] and len(compare.queries) == 3
    assert all(request["maxVisits"] == 30 for request, _ in compare.queries)
    judge(compare, 0, answer_score=2.0)
    assert saved.answers == [("p1", True, 30, True)]


def test_without_katago_the_answer_is_saved_without_losses():
    """When no KataGo can judge, the answer is saved at once without losses, and the screen is told why."""
    run, _, saved = make_run(judging=Judging(None, MAIN, "KataGo is not found"))
    run.answer(point("R4"))
    assert not run.busy and saved.answers == [("p1", None, None, False)]
    assert run.waiting_reason(run.session) == (REASON_NO_ENGINE, {"reason": "KataGo is not found"})


def test_a_failed_judging_is_told_and_saved_without_losses():
    """When KataGo cannot judge, the answer is saved without losses, and the error is told once."""
    run, listener, saved = make_run()
    run.answer(point("R4"))
    engine = run.judging.engine
    engine.answer(0, error="KataGo stopped")
    engine.answer(1, error="KataGo stopped")
    assert not run.busy and saved.answers == [("p1", None, None, False)]
    assert listener.failures[0][0] == REASON_FAILED and "KataGo stopped" in listener.failures[0][1]
    assert run.waiting_reason(run.session)[0] == REASON_FAILED


def test_a_wrong_answer_is_not_asked_again_the_same_day():
    """A problem answered wrong is not added to the quiz: it is reviewed on a later day."""
    run, _, _ = make_run()
    run.answer(point("A19"))
    assert run.session.result.correct is False
    assert [p.problem_id for p in run.problems] == ["p1"]


def test_the_comparison_models_sequence_is_asked_when_chosen():
    """The comparison model's sequence is offered after the answer, and calculated when the user switches to it."""
    main, compare = FakeEngine(), FakeEngine()
    run, listener, _ = make_run(judging=Judging(main, MAIN, "", compare, COMPARE))
    run.answer(point("Q4"))
    session = run.session
    sources = [choice.source for choice in session.choices]
    assert SOURCE_KATAGO_COMPARE in sources
    assert compare.queries == []
    while session.choice.source != SOURCE_KATAGO_COMPARE:
        assert run.next_variation()
    assert len(compare.queries) == 3 and session.choice.status == WAITING
    judge(compare, 0, answer_score=2.0)
    assert session.compare_best is not None and listener.changes[-1] is session


def test_a_failed_comparison_is_told():
    """When the comparison model fails, its sequence is marked as failed and the error is told."""
    main, compare = FakeEngine(), FakeEngine()
    run, listener, _ = make_run(judging=Judging(main, MAIN, "", compare, COMPARE))
    run.answer(point("Q4"))
    session = run.session
    while session.choice.source != SOURCE_KATAGO_COMPARE:
        run.next_variation()
    compare.answer(0, error="no model")
    compare.answer(1, error="no model")
    assert session.choice.status == FAILED
    assert listener.failures[0][0] == "notice_compare_line_failed"


def test_without_the_comparison_model_nothing_is_offered():
    """Without the comparison model, its sequence is not offered."""
    run, _, _ = make_run()
    run.answer(point("Q4"))
    assert all(choice.status != OFFERED for choice in run.session.choices)


def test_answers_still_judged_are_saved_when_the_screen_is_left():
    """When the screen is left, the answers KataGo still judges are saved without losses, and not again later."""
    run, _, saved = make_run()
    run.answer(point("R4"))
    run.save_unfinished()
    assert saved.answers == [("p1", None, None, False)] and not run.busy
    judge(run.judging.engine, 0, answer_score=1.5)
    assert len(saved.answers) == 1


def test_an_illegal_move_is_refused():
    """A move on a stone is refused with the reason; nothing is judged or saved."""
    run, _, saved = make_run()
    assert run.answer(point("Q16")) != ""
    assert run.session.phase != ANSWERED and saved.answers == []
    assert run.answer(point("Q4")) == "" and run.answer(point("R4")) == ""  # A second answer is ignored.


def test_katagos_answers_pass_through_the_main_thread():
    """Every callback of KataGo is wrapped by in_main (the screen runs it in its main thread)."""
    wrapped = []

    def in_main(function):
        wrapped.append(function)
        return function

    run, _, _ = make_run(in_main=in_main)
    run.answer(point("R4"))
    assert len(wrapped) == 2  # The result and the error of the judging.


def test_the_judging_chooses_the_model_and_its_visits():
    """The model that judges is the comparison model only when it is there and chosen."""
    main, compare = FakeEngine(), FakeEngine()
    judging = Judging(main, MAIN, "", compare, COMPARE, judge_with_compare=True)
    assert (judging.judge_engine, judging.judge_settings) == (compare, COMPARE)
    without = replace(judging, compare_engine=None)
    assert (without.judge_engine, without.judge_settings, without.judges_with_compare) == (main, MAIN, False)
    models = judging.models()
    assert (models.main.engine, models.compare.engine, models.compare.settings) == (main, compare, COMPARE)
    assert Judging().models().main is None


@pytest.mark.parametrize("judge_with_compare", [False, True])
def test_sgf_losses_are_used_only_with_the_main_model(judge_with_compare):
    """The losses in the file come from KaTrain's model, so they are not used when the comparison model judges."""
    judging = Judging(FakeEngine(), MAIN, "", FakeEngine(), COMPARE, judge_with_compare)
    run, _, _ = make_run(judging=judging)
    run.answer(point("Q4"))
    assert (run.session.result.correct is None) == judge_with_compare
