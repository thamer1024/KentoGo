"""Tests for kentogo.quiz.quiz_run, with fake KataGo engines and a listener that keeps what it is told."""

from dataclasses import replace

from fake_analysis import FakeEngine

from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import EvaluationSettings
from kentogo.mistakes.problem import (
    SOURCE_BEST_HUMAN,
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
    run.judging.engine.answer(2, score=-6.0, pv=("R17",))
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
    # The sequence after the answer, and the first move of the sequence from the problem position.
    assert [request["moves"][-1] for request, _ in engine.queries] == [["B", "Q4"], ["W", "D4"]]
    engine.answer(0, error="KataGo stopped")
    engine.answer(1, error="KataGo stopped")
    statuses = {choice.source: choice.status for choice in session.choices}
    assert statuses == {SOURCE_RANK_ANSWER: FAILED, SOURCE_BEST_HUMAN: FAILED}
    assert not run.calculating and listener.changes == [session, session]


def test_the_game_move_gets_two_sequences():
    """When the answer is the game move, KataGo is asked for the sequences, as for any answer."""
    run, _, saved = make_run()
    run.answer(point("A19"))
    assert len(run.judging.engine.queries) == 2 and saved.answers == [("p1", False, None)]


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


def human_policy_two_answer(engine: FakeEngine, index: int, first: tuple[int, int], second: tuple[int, int]) -> None:
    """Answer a query for the human-like policy: two points have the chances 0.5 and 0.45 (no other is likely)."""
    policy = [0.001] * (19 * 19 + 1)
    policy[(18 - first[1]) * 19 + first[0]] = 0.5
    policy[(18 - second[1]) * 19 + second[0]] = 0.45
    engine.queries[index][1]({"id": "x", "isDuringSearch": False, "humanPolicy": policy})


def answered_with_rank(rank: str, mine: str = "", the_problem=None, log=lambda _record: None):
    """Answer R4 (KataGo judges it); KataGo's own sequences are R4 D16 (the answer) and A19 R17 (the game move).

    After the judging (the queries 0 to 2), the queries 3 and 4 are the first moves of the sequence after the
    answer (the opponent's) and of the sequence from the problem position (the user's).
    """
    main = FakeEngine()
    ranks = PlayerRanks(mine, rank)
    judging = Judging(main, MAIN, player_ranks=lambda _problem: ranks, log_line=log)
    run, listener, _ = make_run([the_problem or problem()], judging)
    run.answer(point("R4"))
    judge(main, 0, answer_score=1.5)
    return main, run.session, listener


def shown_moves(session, source: str) -> tuple[str, ...]:
    """The moves of the sequence of a source."""
    [choice] = [choice for choice in session.choices if choice.source == source]
    return tuple(move.gtp() for move in choice.variation.moves) if choice.variation else ()


def profile_of(engine: FakeEngine, index: int) -> str:
    """The human-like profile that a query asks for."""
    return engine.queries[index][0]["overrideSettings"]["humanSLProfile"]


def human_queries(engine: FakeEngine) -> list[int]:
    """The indexes of the queries for the human-like policy."""
    return [index for index, (request, _) in enumerate(engine.queries) if request.get("includePolicy")]


def test_the_sequence_after_the_answer_has_the_human_like_replies(monkeypatch):
    """After the answer, both players play as humans of their ranks, in the first sequence of Tab."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)  # Not made longer than KataGo's own sequence.
    main, session, listener = answered_with_rank("10k", mine="15k")
    statuses = [(choice.source, choice.status) for choice in session.choices]
    assert statuses == [(SOURCE_RANK_ANSWER, WAITING), (SOURCE_BEST_HUMAN, WAITING)] and session.shows_verdict
    assert human_queries(main) == [3, 4]
    assert profile_of(main, 3) == "rank_10k"  # The opponent's reply after the answer.
    human_policy_answer(main, 3, 2, 15)  # The opponent's C16.
    assert shown_moves(session, SOURCE_RANK_ANSWER) == ("R4", "C16") and session.variation_index == 0
    assert listener.changes[-1] is session


def test_without_the_opponents_rank_the_opponent_replies_of_the_users_rank():
    """When only the user's rank is known, the opponent plays as a human of that rank."""
    main, _, _ = answered_with_rank("", mine="15k")
    assert [profile_of(main, index) for index in human_queries(main)] == ["rank_15k", "rank_15k"]


def test_without_the_users_rank_the_user_plays_as_a_human_of_the_opponents_rank():
    """When only the opponent's rank is known, the user's moves are human-like of that rank."""
    main, _, _ = answered_with_rank("10k")
    assert [profile_of(main, index) for index in human_queries(main)] == ["rank_10k", "rank_10k"]


def test_without_a_rank_katagos_own_moves_are_used(monkeypatch):
    """Without any rank, the sequence after the answer is KataGo's own, and the other has its best moves."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)  # Not made longer than KataGo's own sequence.
    main, session, _ = answered_with_rank("")
    assert human_queries(main) == []
    assert shown_moves(session, SOURCE_RANK_ANSWER) == ("R4", "D16")
    assert main.queries[3][0]["maxVisits"] == MAIN.estimate_visits  # The user's best move from the problem position.
    main.answer(3, score=1.0, pv=("Q4",))
    assert shown_moves(session, SOURCE_BEST_HUMAN) == ("Q4",)


def test_without_the_human_like_model_katagos_own_sequence_is_shown(monkeypatch):
    """When KataGo gives no human-like policy, its own sequence after the answer is shown, and why is told."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)
    main, session, listener = answered_with_rank("10k", mine="15k")
    main.queries[3][1]({"id": "x", "isDuringSearch": False, "rootInfo": {"scoreLead": 0.0}})
    assert shown_moves(session, SOURCE_RANK_ANSWER) == ("R4", "D16")
    assert listener.failures[-1][0] == "notice_human_line_failed"


def test_the_sequence_from_the_problem_position_starts_with_the_users_human_like_move(monkeypatch):
    """The user's first move is the only likely move of a human of the user's rank (no search is needed)."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)
    main, session, listener = answered_with_rank("10k", mine="15k")
    assert profile_of(main, 4) == "rank_15k"
    human_policy_answer(main, 4, 16, 15)  # R16.
    assert len(main.queries) == 5  # No search for the only candidate.
    assert shown_moves(session, SOURCE_BEST_HUMAN) == ("R16",) and listener.changes[-1] is session


def search_answer(engine: FakeEngine, index: int, scores: dict[str, float]) -> None:
    """Answer a search of the candidates: the score lead (from black's side) after each of them."""
    infos = [
        {"move": move, "order": order, "scoreLead": lead, "pv": [move]}
        for order, (move, lead) in enumerate(scores.items())
    ]
    engine.queries[index][1]({"id": "x", "isDuringSearch": False, "rootInfo": {"scoreLead": 0.0}, "moveInfos": infos})


def events(records: list[dict], event: str) -> list[dict]:
    """The records of the log of an event."""
    return [record for record in records if record["event"] == event]


def test_the_user_plays_the_least_loss_of_the_candidates_and_the_log_tells_it(monkeypatch):
    """KataGo reads only the candidates (max_visits for the first move, no noise); the least loss is played."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)
    records = []
    main, session, _ = answered_with_rank("10k", mine="15k", log=records.append)
    human_policy_two_answer(main, 4, (2, 15), (16, 15))  # C16 (more likely) and R16.
    search = main.queries[5][0]
    assert search["allowMoves"] == [{"player": "B", "moves": ["C16", "R16"], "untilDepth": 1}]
    assert search["maxVisits"] == MAIN.max_visits and "humanSLProfile" not in search["overrideSettings"]
    search_answer(main, 5, {"R16": 2.0, "C16": 1.2})  # C16 loses 0.8 points: R16 is played.
    assert shown_moves(session, SOURCE_BEST_HUMAN) == ("R16",)
    [record] = events(records, "human_best_move")
    assert (record["problem"], record["how"], record["chosen"], record["chosen_loss"]) == ("p1", "search", "R16", 0.0)
    assert record["line"] == "best"
    assert record["visits"] == MAIN.max_visits
    assert record["candidates"] == [
        {"move": "C16", "chance": 0.5, "loss": 0.8},
        {"move": "R16", "chance": 0.45, "loss": 0.0},
    ]
    # KataGo then reads the position without a limit, and the log tells the loss against the best move of all.
    assert main.queries[6][0].get("allowMoves") is None
    main.answer(6, score=2.5, pv=("Q3",))
    [reference] = events(records, "human_best_reference")
    assert (reference["best"], reference["loss_against_best"], reference["chosen"]) == ("Q3", 0.5, "R16")


def test_among_equally_good_candidates_the_most_likely_one_is_played(monkeypatch):
    """Candidates within the tolerance of the least loss are equal: the most likely one is played."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)
    main, session, _ = answered_with_rank("10k", mine="15k")
    human_policy_two_answer(main, 4, (2, 15), (16, 15))
    search_answer(main, 5, {"R16": 1.2, "C16": 1.0})  # C16 loses 0.2 points only.
    assert shown_moves(session, SOURCE_BEST_HUMAN) == ("C16",)


def test_when_katago_reads_none_of_the_candidates_the_most_likely_one_is_played(monkeypatch):
    """Without a loss for any candidate (nothing read), the most likely candidate is played, and the log tells it."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 1)
    records = []
    main, session, _ = answered_with_rank("10k", mine="15k", log=records.append)
    human_policy_two_answer(main, 4, (2, 15), (16, 15))
    search_answer(main, 5, {})
    assert shown_moves(session, SOURCE_BEST_HUMAN) == ("C16",)
    assert events(records, "human_best_move")[0]["how"] == "fallback"
    assert len(main.queries) == 6  # No reading of the position without a limit.


def test_the_reading_without_a_limit_waits_for_the_end_of_the_sequence_and_the_log_tells_the_end(monkeypatch):
    """The reading for the log does not slow down the moves: it comes after the last move, and the end is logged."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 4)
    records = []
    main, session, _ = answered_with_rank("10k", mine="15k", log=records.append)
    human_policy_answer(main, 4, 16, 15)  # The user's R16.
    human_policy_answer(main, 5, 2, 15)  # The opponent's C16.
    human_policy_two_answer(main, 6, (16, 3), (14, 3))  # The user's R4 or P4.
    search_answer(main, 7, {"R4": 0.0, "P4": 5.0})  # P4 is played.
    assert main.queries[8][0].get("includePolicy")  # The next query is for the opponent's move, not the reading.
    assert events(records, "human_best_reference") == [] and events(records, "human_line_end") == []
    human_policy_answer(main, 8, 3, 15)  # The opponent's D16: the fourth move, the aimed length.
    [end] = [record for record in events(records, "human_line_end") if record["line"] == "best"]
    assert (end["moves"], end["aimed"], end["reason"]) == (4, 4, "length")
    assert main.queries[9][0]["maxVisits"] == MAIN.estimate_visits * quiz_run.LATER_VISITS_FACTOR
    assert not main.queries[9][0].get("includePolicy") and "allowMoves" not in main.queries[9][0]


def test_the_aimed_length_follows_the_games_own_moves():
    """The sequences are made as long as the game's moves after the problem: at least MIN_LINE, at most MAX_LINE."""
    moves = tuple(Move.from_gtp("A19", "B" if number % 2 == 0 else "W") for number in range(30))
    aimed = quiz_run._aimed_length
    assert aimed(problem()) == quiz_run.MIN_LINE
    assert aimed(replace(problem(), game_line=moves[:14])) == 14
    assert aimed(replace(problem(), game_line=moves)) == quiz_run.MAX_LINE


def test_all_the_users_moves_of_the_sequence_from_the_problem_position_are_chosen_among_the_candidates(monkeypatch):
    """The opponent plays human-like moves of the opponent's rank; the user's later moves read more visits."""
    monkeypatch.setattr(quiz_run, "MIN_LINE", 3)
    main, session, _ = answered_with_rank("10k", mine="15k")
    human_policy_answer(main, 4, 16, 15)  # The user's R16.
    assert profile_of(main, 5) == "rank_10k"
    human_policy_answer(main, 5, 2, 15)  # The opponent's C16.
    assert profile_of(main, 6) == "rank_15k"
    human_policy_two_answer(main, 6, (16, 3), (14, 3))  # The user's R4 or P4.
    search = main.queries[7][0]
    assert search["allowMoves"][0]["moves"] == ["R4", "P4"]
    assert search["maxVisits"] == MAIN.estimate_visits * quiz_run.LATER_VISITS_FACTOR
    search_answer(main, 7, {"R4": 0.0, "P4": 5.0})  # R4 loses 5 points.
    assert shown_moves(session, SOURCE_BEST_HUMAN) == ("R16", "C16", "P4")


def test_a_failed_sequence_from_the_problem_position_is_marked():
    """When KataGo cannot make it, the sequence stays in the order as failed."""
    main, session, _ = answered_with_rank("10k", mine="15k")
    main.answer(4, error="KataGo stopped")
    statuses = {choice.source: choice.status for choice in session.choices}
    assert statuses[SOURCE_BEST_HUMAN] == FAILED


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


def test_the_best_move_is_told_as_coming_as_soon_as_the_answer_is_taken():
    """From the answer on, the screen can say that KataGo is thinking, and KataGo's best of the analysis is not shown."""
    run, _, _ = make_run()
    run.answer(point("R4"))  # Judged by KataGo: it is not done yet.
    session = run.session
    assert run.busy and session.best_move_waiting and session.best_move is None
    judge(run.judging.engine, 0, answer_score=1.5)
    assert session.best_move_waiting  # The sequence from the problem position is being made.
    known, _, _ = make_run()
    known.answer(point("Q4"))  # Judged from the file.
    assert known.session.best_move_waiting and known.session.best_move is None


def test_without_katago_or_after_a_failure_no_best_move_is_shown_and_none_is_awaited():
    """No KataGo: no sequence is expected. A failed judging: the sequence from the problem position fails too."""
    run, _, _ = make_run(judging=Judging(None, MAIN, "KataGo is not found"))
    run.answer(point("R4"))
    assert not run.session.best_move_waiting and run.session.best_move is None
    failed, _, _ = make_run()
    failed.answer(point("R4"))
    failed.judging.engine.answer(0, error="KataGo stopped")
    failed.judging.engine.answer(1, error="KataGo stopped")
    assert not failed.session.best_move_waiting and failed.session.best_move is None
