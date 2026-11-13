"""Tests for kentogo.quiz.quiz_run, with fake KataGo engines and a listener that keeps what it is told."""

from fake_analysis import FakeEngine

from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import EvaluationSettings
from kentogo.mistakes.problem import (
    SOURCE_KATAGO_ANSWER,
    SOURCE_RANK_ANSWER,
    Problem,
    Variation,
)
from kentogo.quiz import quiz_run
from kentogo.quiz.human_line import PlayerRanks
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.quiz_run import REASON_EVALUATING, REASON_FAILED, REASON_NO_ENGINE, Judging, QuizRun
from kentogo.quiz.session import ANSWERED, FAILED, WAITING
from kentogo.quiz.transform import BoardTransform

MAIN = EvaluationSettings(max_visits=100)


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
    """Keeps the saved answers as (problem ID, correct, visits)."""

    def __init__(self):
        """Start with nothing saved."""
        self.answers: list[tuple] = []

    def __call__(self, session, max_visits):
        """Keep one saved answer."""
        self.answers.append((session.problem.problem_id, session.result.correct, max_visits))


def make_run(problems=None, judging=None, **values):
    """Make a quiz with a fake engine and start it."""
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
    assert run.next_problem()
    assert listener.started_with[-1].problem.problem_id == "p2"
    run.answer(point("A19"))
    run.judging.engine.answer(1, score=-6.0, pv=("R17",))
    assert run.next_problem() and listener.started_with[-1] is None and run.session is None
    assert not run.next_problem()  # After the end, nothing happens.


def test_an_answer_in_the_file_is_judged_at_once_and_saved():
    """The best move is judged from the file: it is saved once, and KataGo shows the sequence after it."""
    run, listener, saved = make_run()
    assert run.answer(point("Q4")) == ""
    session = run.session
    assert session.phase == ANSWERED and session.result.correct is True
    assert saved.answers == [("p1", True, None)]
    assert not run.busy and run.calculating  # The sequences are still being calculated.
    engine = run.judging.engine
    assert [request["moves"][-1] for request, _ in engine.queries] == [["B", "Q4"]]
    engine.answer(0, error="KataGo stopped")
    statuses = {choice.source: choice.status for choice in session.choices}
    assert statuses[SOURCE_KATAGO_ANSWER] == FAILED
    assert not run.calculating and listener.changes == [session]


def test_the_game_move_gets_one_sequence():
    """When the answer is the game move, KataGo is asked for the sequence after it, as for any answer."""
    run, _, saved = make_run()
    run.answer(point("A19"))
    assert len(run.judging.engine.queries) == 1 and saved.answers == [("p1", False, None)]


def test_other_answers_are_judged_by_katago():
    """While KataGo judges, the quiz is busy and tells why; the losses are kept and the answer is saved then."""
    run, listener, saved = make_run()
    run.answer(point("R4"))
    session = run.session
    assert run.busy and run.calculating and not run.can_play()
    assert run.waiting_reason(session) == (REASON_EVALUATING, {})
    assert not run.next_variation()
    assert not run.previous_variation()  # Not while KataGo judges.
    assert saved.answers == []
    judge(run.judging.engine, 0, answer_score=1.5)  # The answer loses 0.5 points.
    assert not run.busy and run.can_play() and run.waiting_reason(session) is None
    assert session.result.correct is True and saved.answers == [("p1", True, 100)]
    assert listener.changes == [session]


def test_without_katago_the_answer_is_saved_without_losses():
    """When no KataGo can judge, the answer is saved at once without losses, and the screen is told why."""
    run, _, saved = make_run(judging=Judging(None, MAIN, "KataGo is not found"))
    run.answer(point("R4"))
    assert not run.busy and saved.answers == [("p1", None, None)]
    assert run.waiting_reason(run.session) == (REASON_NO_ENGINE, {"reason": "KataGo is not found"})


def test_a_failed_judging_is_told_and_saved_without_losses():
    """When KataGo cannot judge, the answer is saved without losses, and the error is told once."""
    run, listener, saved = make_run()
    run.answer(point("R4"))
    engine = run.judging.engine
    engine.answer(0, error="KataGo stopped")
    engine.answer(1, error="KataGo stopped")
    assert not run.busy and saved.answers == [("p1", None, None)]
    assert listener.failures[0][0] == REASON_FAILED and "KataGo stopped" in listener.failures[0][1]
    assert run.waiting_reason(run.session)[0] == REASON_FAILED


def test_a_wrong_answer_is_not_asked_again_the_same_day():
    """A problem answered wrong is not added to the quiz: it is reviewed on a later day."""
    run, _, _ = make_run()
    run.answer(point("A19"))
    assert run.session.result.correct is False
    assert [p.problem_id for p in run.problems] == ["p1"]


def test_answers_still_judged_are_saved_when_the_screen_is_left():
    """When the screen is left, the answers KataGo still judges are saved without losses, and not again later."""
    run, _, saved = make_run()
    run.answer(point("R4"))
    run.save_unfinished()
    assert saved.answers == [("p1", None, None)] and not run.busy
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


def test_the_judging_gives_the_main_model():
    main = FakeEngine()
    assert Judging(main, MAIN).models().main.engine is main
    assert Judging().models().main is None


def human_policy_answer(engine: FakeEngine, index: int, x: int, y: int) -> None:
    """Answer a query for the human-like policy of a 19x19 board: the point (x, y) has the biggest chance."""
    policy = [0.001] * (19 * 19 + 1)
    policy[(18 - y) * 19 + x] = 0.9
    engine.queries[index][1]({"id": "x", "isDuringSearch": False, "humanPolicy": policy})


def answered_with_rank(rank: str, mine: str = ""):
    """Answer R4 (KataGo judges it); KataGo's own sequences are R4 D16 (the answer) and A19 R17 (the game move)."""
    main = FakeEngine()
    ranks = PlayerRanks(mine, rank)
    run, listener, _ = make_run(judging=Judging(main, MAIN, player_ranks=lambda _problem: ranks))
    run.answer(point("R4"))
    judge(main, 0, answer_score=1.5)
    return main, run.session, listener


def shown_moves(session, source: str) -> tuple[str, ...]:
    """The moves of the sequence of a source."""
    [choice] = [choice for choice in session.choices if choice.source == source]
    return tuple(move.gtp() for move in choice.variation.moves) if choice.variation else ()


def human_queries(engine: FakeEngine) -> list[int]:
    """The indexes of the queries for the human-like policy."""
    return [index for index, (request, _) in enumerate(engine.queries) if request.get("includePolicy")]


def strongest_queries(engine: FakeEngine, first: int = 3) -> list[int]:
    """The indexes of the queries for best moves from `first` on (after the judging), not for the human-like policy."""
    return [
        index
        for index, (request, _) in enumerate(engine.queries)
        if index >= first and not request.get("includePolicy")
    ]


def after(indexes: list[int], first: int) -> list[int]:
    """The indexes after `first` (not the queries of the sequence with the replies of the opponent's rank)."""
    return [index for index in indexes if index > first]


def test_the_sequence_with_the_replies_of_the_opponents_rank_comes_first(monkeypatch):
    """After the answer, the opponent replies as a human of the opponent's rank, in the first sequence of Tab."""
    monkeypatch.setattr(quiz_run, "LINE_SECONDS", -1.0)  # Not made longer than KataGo's own sequence.
    main, session, listener = answered_with_rank("10k", mine="15k")
    assert (session.choices[0].source, session.choices[0].status) == (SOURCE_RANK_ANSWER, WAITING)
    assert session.choices[1].source == SOURCE_KATAGO_ANSWER and session.shows_verdict
    [theirs] = human_queries(main)
    assert main.queries[theirs][0]["overrideSettings"]["humanSLProfile"] == "rank_10k"
    human_policy_answer(main, theirs, 2, 15)  # The opponent's C16.
    assert shown_moves(session, SOURCE_RANK_ANSWER) == ("R4", "C16") and session.variation_index == 0
    assert listener.changes[-1] is session


def test_without_the_opponents_rank_the_opponent_replies_of_the_users_rank():
    """When only the user's rank is known, the opponent of the first sequence plays as a human of that rank."""
    main, _, _ = answered_with_rank("", mine="15k")
    [theirs] = human_queries(main)
    assert main.queries[theirs][0]["overrideSettings"]["humanSLProfile"] == "rank_15k"


def test_without_a_rank_there_is_no_sequence_with_the_replies_of_a_rank():
    """Without any rank, KataGo's own sequences only."""
    _, session, _ = answered_with_rank("")
    assert SOURCE_RANK_ANSWER not in [choice.source for choice in session.choices]


def test_the_sequence_after_the_answer_has_the_strongest_replies(monkeypatch):
    """With a rank, the opponent replies with the main KataGo's best moves, reading estimate_visits each."""
    monkeypatch.setattr(quiz_run, "LINE_SECONDS", -1.0)  # Not made longer than KataGo's own sequence.
    main, session, listener = answered_with_rank("10k")
    statuses = {choice.source: choice.status for choice in session.choices}
    assert statuses[SOURCE_KATAGO_ANSWER] == WAITING
    [first] = strongest_queries(main)
    assert main.queries[first][0]["maxVisits"] == MAIN.estimate_visits
    assert "humanSLProfile" not in main.queries[first][0].get("overrideSettings", {})
    main.answer(first, score=1.0, pv=("C16",))
    assert shown_moves(session, SOURCE_KATAGO_ANSWER) == ("R4", "C16")
    assert listener.changes[-1] is session


def test_without_a_rank_katagos_own_sequences_are_shown():
    """Without the opponent's rank, KataGo's own sequences are shown at once."""
    main, session, _ = answered_with_rank("")
    assert human_queries(main) == []
    assert shown_moves(session, SOURCE_KATAGO_ANSWER) == ("R4", "D16")


def test_without_the_human_like_model_katagos_own_sequences_are_shown(monkeypatch):
    """When KataGo gives no human-like policy for the user's move, its own sequence is shown, and why is told."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 3)
    main, session, listener = answered_with_rank("10k")
    [first] = strongest_queries(main)
    main.answer(first, score=1.0, pv=("C16",))
    [mine] = after(human_queries(main), first)
    main.queries[mine][1]({"id": "x", "isDuringSearch": False, "rootInfo": {"scoreLead": 0.0}})
    assert shown_moves(session, SOURCE_KATAGO_ANSWER) == ("R4", "D16")
    assert listener.failures[-1][0] == "notice_human_line_failed"


def test_the_users_moves_are_human_like_of_the_users_rank(monkeypatch):
    """With the user's rank, the user's moves after the opponent's reply are human-like of that rank."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 3)
    main, session, _ = answered_with_rank("10k", mine="15k")
    [first] = strongest_queries(main)
    main.answer(first, score=1.0, pv=("C16",))
    [mine] = after(human_queries(main), first)
    assert main.queries[mine][0]["overrideSettings"]["humanSLProfile"] == "rank_15k"
    human_policy_answer(main, mine, 16, 15)  # The user's R16.
    assert shown_moves(session, SOURCE_KATAGO_ANSWER) == ("R4", "C16", "R16")


def test_without_the_users_rank_the_users_moves_are_human_like_of_the_opponents_rank(monkeypatch):
    """When only the opponent's rank is known, the user's moves are human-like of that rank."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 3)
    main, _, _ = answered_with_rank("10k")
    [first] = strongest_queries(main)
    main.answer(first, score=1.0, pv=("C16",))
    [mine] = after(human_queries(main), first)
    assert main.queries[mine][0]["overrideSettings"]["humanSLProfile"] == "rank_10k"


class StoppingEngine(FakeEngine):
    """A fake KataGo that can stop reading all queries."""

    def __init__(self):
        super().__init__()
        self.stopped = 0

    def terminate_all(self):
        self.stopped += 1


def test_the_next_problem_at_once_while_katago_judges():
    """The next problem is asked at once: the answer is saved without losses, and KataGo stops reading."""
    main = StoppingEngine()
    run, listener, saved = make_run([problem("p1"), problem("p2")], Judging(main, MAIN))
    run.answer(point("R4"))
    first = run.session
    assert run.calculating and run.next_problem()
    assert saved.answers == [("p1", None, None)] and main.stopped == 1
    assert run.session is not first and run.session.problem.problem_id == "p2"
    judge(main, 0, answer_score=1.5)  # A late answer for the problem left is not used.
    assert first.result.correct is None and saved.answers == [("p1", None, None)]


def test_leaving_the_quiz_while_katago_judges_stops_katago():
    """Back to the top screen: the answer still judged is saved without losses, and KataGo stops reading."""
    main = StoppingEngine()
    run, _, saved = make_run([problem("p1"), problem("p2")], Judging(main, MAIN))
    run.answer(point("R4"))
    first = run.session
    run.leave()
    assert saved.answers == [("p1", None, None)] and main.stopped == 1
    judge(main, 0, answer_score=1.5)  # A late answer is not used.
    assert first.result.correct is None and saved.answers == [("p1", None, None)]


def test_leaving_the_quiz_without_calculations_does_not_stop_katago():
    """Back to the top screen when nothing is calculated: KataGo is not told to stop, and nothing is saved."""
    main = StoppingEngine()
    run, _, saved = make_run([problem("p1")], Judging(main, MAIN))
    run.leave()
    assert main.stopped == 0 and saved.answers == []


def test_the_next_problem_without_calculations_does_not_stop_katago():
    main = StoppingEngine()
    run, _, _ = make_run([problem("p1"), problem("p2")], Judging(main, MAIN))
    assert run.next_problem() and main.stopped == 0
