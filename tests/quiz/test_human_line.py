"""Tests for kentogo.quiz.human_line (the comparison model's sequence with the opponent's human-like replies)."""

from fake_analysis import FakeEngine

from kentogo.common.types import GTP_COLUMNS, Move, Position, moves_from_gtp
from kentogo.quiz.human_line import Extension, LineEngines, build_line, build_line_from_start

POSITION = Position(19, 6.5, "japanese", (), (Move.from_gtp("Q16", "B"), Move.from_gtp("D4", "W")), "B")
OWN_LINE = moves_from_gtp(("Q4", "D16", "R17", "C3"), "B")  # The comparison model's own sequence.


def human_answer(engine: FakeEngine, index: int, gtp: str) -> None:
    """Answer a query for the human-like policy: the point gtp has the biggest chance."""
    policy = [0.001] * (19 * 19 + 1)
    if gtp == "pass":
        policy[-1] = 0.9
    else:
        x, y = GTP_COLUMNS.index(gtp[0]), int(gtp[1:])
        policy[(19 - y) * 19 + x] = 0.9
    engine.queries[index][1]({"id": "x", "isDuringSearch": False, "humanPolicy": policy})


def build(first_line=OWN_LINE):
    """Start the sequence with fake engines, and return them with what the sequence ended with."""
    best, human, ended = FakeEngine(), FakeEngine(), {}
    engines = LineEngines(best, human, 50, 0.04, "rank_10k")
    build_line(
        engines,
        POSITION,
        first_line,
        on_done=lambda line: ended.update(line=line),
        on_error=lambda message: ended.update(error=message),
    )
    return best, human, ended


def test_the_opponents_moves_are_human_like_and_the_users_the_best():
    """The user's moves are the comparison model's best moves, the opponent's the human-like ones, as long as before."""
    best, human, ended = build()
    assert ended == {} and len(human.queries) == 1
    request = human.queries[0][0]
    assert request["overrideSettings"]["humanSLProfile"] == "rank_10k" and request["moves"][-1] == ["B", "Q4"]
    human_answer(human, 0, "C16")
    assert best.queries[0][0]["maxVisits"] == 50 and best.queries[0][0]["moves"][-1] == ["W", "C16"]
    best.answer(0, score=1.0, pv=("R16", "C17"))
    human_answer(human, 1, "C17")
    assert ended == {"line": moves_from_gtp(("Q4", "C16", "R16", "C17"), "B")}


def test_the_sequence_ends_at_a_pass():
    """When the opponent would most likely pass, the sequence ends there."""
    _best, human, ended = build()
    human_answer(human, 0, "pass")
    assert ended["line"] == (Move.from_gtp("Q4", "B"), Move("W", None))


def test_an_answer_without_the_human_like_policy_is_an_error():
    """Without the human-like model, KataGo gives no human-like policy: the error is told."""
    _best, human, ended = build()
    human.queries[0][1]({"id": "x", "isDuringSearch": False, "rootInfo": {"scoreLead": 0.0}})
    assert "human-like" in ended["error"]


def test_an_error_of_the_best_moves_query_is_told():
    """An error of the query for a best move is told."""
    best, human, ended = build()
    human_answer(human, 0, "C16")
    best.answer(0, error="broken")
    assert "broken" in ended["error"]


def test_a_short_sequence():
    """A sequence of one move needs no query, and no sequence gives none."""
    best, human, ended = build(OWN_LINE[:1])
    assert ended == {"line": OWN_LINE[:1]} and best.queries == human.queries == []
    assert build(())[2] == {"line": ()}


def test_the_users_moves_are_human_like_with_the_users_profile():
    """With my_profile, the user's moves are asked for the human-like policy too, not the best moves."""
    best, human, ended = FakeEngine(), FakeEngine(), {}
    engines = LineEngines(best, human, 50, 0.04, "rank_10k", my_profile="rank_15k")
    build_line(engines, POSITION, OWN_LINE[:3], lambda line: ended.update(line=line), print)
    human_answer(human, 0, "C16")
    assert human.queries[1][0]["overrideSettings"]["humanSLProfile"] == "rank_15k" and best.queries == []
    human_answer(human, 1, "R16")
    assert ended["line"] == moves_from_gtp(("Q4", "C16", "R16"), "B")


def test_the_sequence_is_made_longer_up_to_the_aimed_length():
    """After its own length, moves are added up to the aimed length, however long it takes."""
    best, human, ended = FakeEngine(), FakeEngine(), {}
    engines = LineEngines(best, human, 50, 0.04, "rank_10k")
    build_line(engines, POSITION, OWN_LINE[:2], lambda line: ended.update(line=line), print, Extension(4))
    human_answer(human, 0, "C16")  # The second move: the own length is reached, the aimed length is not.
    assert ended == {}
    best.answer(0, score=1.0, pv=("R16",))
    assert ended == {}
    human_answer(human, 1, "C17")
    assert ended == {"line": moves_from_gtp(("Q4", "C16", "R16", "C17"), "B")}


def test_the_own_length_is_made_even_when_it_is_longer_than_the_aimed_length():
    """The moves up to KataGo's own length are always made."""
    best, human, ended = FakeEngine(), FakeEngine(), {}
    engines = LineEngines(best, human, 50, 0.04, "rank_10k")
    build_line(engines, POSITION, OWN_LINE[:3], lambda line: ended.update(line=line), print, Extension(2))
    human_answer(human, 0, "C16")
    assert ended == {}  # Still shorter than its own length.
    best.answer(0, score=1.0, pv=("R16",))
    assert ended == {"line": moves_from_gtp(("Q4", "C16", "R16"), "B")}


def test_the_sequence_from_the_problem_position_is_made_up_to_the_aimed_length():
    """It starts with the user's move (here KataGo's best), and goes on to the aimed length."""
    best, human, ended = FakeEngine(), FakeEngine(), {}
    engines = LineEngines(best, human, 50, None, "")
    build_line_from_start(engines, POSITION, lambda line: ended.update(line=line), print, Extension(3))
    best.answer(0, score=1.0, pv=("Q4",))
    best.answer(1, score=1.0, pv=("D16",))
    assert ended == {}
    best.answer(2, score=1.0, pv=("R17",))
    assert ended == {"line": moves_from_gtp(("Q4", "D16", "R17"), "B")}


def test_the_readings_have_the_users_time_limit():
    """The time of a reading is limited by KataGo itself (maxTime), not by a clock of KentoGo."""
    best, human = FakeEngine(), FakeEngine()
    engines = LineEngines(best, human, 50, None, "", max_time=8.0)
    build_line_from_start(engines, POSITION, lambda _line: None, print, Extension(2))
    assert best.queries[0][0]["overrideSettings"]["maxTime"] == 8.0


def test_the_end_of_the_sequence_is_logged_with_its_reason():
    """The log tells how long the sequence is, how long was aimed at, and why it ended."""
    best, human, records = FakeEngine(), FakeEngine(), []
    engines = LineEngines(best, human, 50, None, "", log=records.append)
    build_line_from_start(engines, POSITION, lambda _line: None, print, Extension(2))
    best.answer(0, score=1.0, pv=("Q4",))
    best.answer(1, score=1.0, pv=("D16",))
    assert records == [{"event": "human_line_end", "moves": 2, "own": 1, "aimed": 2, "reason": "length"}]
    pass_records = []
    engines = LineEngines(best, human, 50, None, "", log=pass_records.append)
    build_line_from_start(engines, POSITION, lambda _line: None, print, Extension(5))
    best.answer(2, score=1.0, pv=("pass",))
    assert [(r["reason"], r["moves"]) for r in pass_records] == [("pass", 1)]


def test_without_a_profile_the_own_sequence_is_kept_and_made_longer():
    """Without the opponent's rank, KataGo's own sequence is kept, and the moves after it are the best moves."""
    best, human, ended = FakeEngine(), FakeEngine(), {}
    engines = LineEngines(best, human, 50, None, "")
    build_line(engines, POSITION, OWN_LINE[:2], lambda line: ended.update(line=line), print, Extension(3))
    assert best.queries[0][0]["moves"][-2:] == [["B", "Q4"], ["W", "D16"]]
    best.answer(0, score=1.0, pv=("R17",))
    assert human.queries == [] and ended == {"line": moves_from_gtp(("Q4", "D16", "R17"), "B")}
