"""Tests for kentogo.quiz.fight_run (a local fight played against a fake KataGo)."""

from dataclasses import replace

from test_fight_judge import fight

from kentogo.common.types import Move, Position
from kentogo.quiz.fight_judge import (
    OPPONENT_RANK,
    OUTCOME_LOST,
    OUTCOME_OPPONENT_LEFT,
    OUTCOME_USER_LEFT,
    OUTCOME_WON,
)
from kentogo.quiz.fight_run import FightPlay, FightRun

STONES = ((0, 0), (1, 0), (2, 0))  # The judged points: black's stones A1, B1 and C1.


def areas(value: float) -> list[float]:
    """The ownership of a 9x9 board (row by row from the top) with the judged points at value, 0 elsewhere."""
    values = [0.0] * 81
    for x, y in STONES:
        values[(8 - y) * 9 + x] = value
    return values


class FakeEngine:
    """Answers at once: black's lead and the areas by the number of moves after the position, the best move, and
    the human-like move (B2 for white)."""

    def __init__(self, by_moves: dict[int, tuple[float, float, str]]):
        self.by_moves = by_moves  # Moves after the position: (black's lead, ownership of the stones, best move).
        self.queries = []

    def query(self, request, callback):
        self.queries.append(request)
        count = len(request["moves"]) - 1  # The position has one move.
        lead, owner, best = self.by_moves[count]
        callback({"isDuringSearch": True})
        if "humanSLProfile" in request["overrideSettings"]:
            policy = [0.0] * 82
            policy[7 * 9 + 1] = 1.0  # B2.
            callback({"rootInfo": {"scoreLead": lead}, "moveInfos": [], "humanPolicy": policy})
            return "x"
        answer = {"rootInfo": {"scoreLead": lead}, "moveInfos": [{"move": best, "order": 0, "pv": [best]}]}
        if request.get("includeOwnership"):
            answer["ownership"] = areas(owner)
        callback(answer)
        return "x"


def run(engine, **play) -> tuple[FightRun, list]:
    events = []
    fight_run = FightRun(engine, fight(), FightPlay(500, 0.04, **play))
    fight_run.start(lambda: events.append("ready"), lambda message: events.append(("error", message)))
    return fight_run, events


def user(fight_run: FightRun, events: list, point: str) -> None:
    fight_run.play(
        Move.from_gtp(point, "B"),
        lambda reply: events.append(("reply", reply.gtp())),
        lambda outcome: events.append(("end", outcome.kind, outcome.score_loss)),
        lambda message: events.append(("error", message)),
    )


def test_the_fight_is_played_until_it_is_settled():
    """Black plays A2, white answers B2 (KataGo's best), black plays C2, and the stones live: correct."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (0.5, 0.6, "B2"), 2: (0.0, 0.6, "D2"), 3: (0.0, 0.9, "J9")})
    fight_run, events = run(engine)
    user(fight_run, events, "A2")
    user(fight_run, events, "C2")
    assert events == ["ready", ("reply", "B2"), ("end", OUTCOME_WON, 1.0)]
    assert [move.gtp() for move in fight_run.played] == ["A2", "B2", "C2"] and fight_run.outcome.correct
    assert all(query["includeOwnership"] for query in engine.queries[1:])


def test_the_user_leaves_the_fight():
    """A move far from the fight (or a pass) is wrong at once, without asking KataGo."""
    engine = FakeEngine({0: (1.0, 0.6, "B2")})
    fight_run, events = run(engine)
    user(fight_run, events, "J9")
    assert events[-1] == ("end", OUTCOME_USER_LEFT, None) and len(engine.queries) == 1
    assert [move.gtp() for move in fight_run.played] == ["J9"]  # Kept, to be saved with the answer.


def test_a_needless_move_answered_elsewhere():
    """KataGo answers far away, and black's move lost 2 points: it was not needed, so it is wrong."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (-1.0, 0.6, "J9")})
    fight_run, events = run(engine)
    user(fight_run, events, "A2")
    assert events[-1] == ("end", OUTCOME_OPPONENT_LEFT, 2.0)


def test_the_last_needed_move_answered_elsewhere():
    """KataGo answers far away after black's best move (nothing lost): the place is done, and the stones live."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (1.0, 0.6, "J9")})
    fight_run, events = run(engine)
    user(fight_run, events, "A2")
    assert events[-1] == ("end", OUTCOME_WON, 0.0)


def test_points_lost_whatever_the_user_plays_are_not_judged():
    """The stones are white's at the start already: only the score is judged, after the first move."""
    engine = FakeEngine({0: (1.0, -0.6, "B2"), 1: (0.5, -0.6, "B2")})
    fight_run, events = run(engine)
    assert fight_run.points == []
    user(fight_run, events, "A2")
    assert events[-1] == ("end", OUTCOME_WON, 0.5)


def test_the_stones_die():
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (-9.0, -0.9, "B2")})
    fight_run, events = run(engine)
    user(fight_run, events, "A2")
    assert events[-1] == ("end", OUTCOME_LOST, 10.0) and not fight_run.outcome.correct


def test_a_human_like_opponent():
    """With the opponent's rank, white plays the human-like move (B2), asked with the profile."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (1.0, 0.6, "C2")})
    fight_run, events = run(engine, opponent=OPPONENT_RANK, profile="rank_15k")
    user(fight_run, events, "A2")
    assert events[-1] == ("reply", "B2")
    assert engine.queries[-1]["overrideSettings"]["humanSLProfile"] == "rank_15k"


def ai_line(engine, **play) -> list:
    fight_run, _events = run(engine, **play)
    lines = []
    fight_run.ask_ai_line(
        lambda _line: None,
        lambda line, _end: lines.append([move.gtp() for move in line]),
        lambda message: lines.append(message),
    )
    return lines


def test_the_sequence_of_the_ais_goes_on_until_the_place_is_settled():
    """Both sides play the human-like moves of their own ranks (also against the strongest opponent)."""
    engine = FakeEngine({0: (1.0, 0.6, "A2"), 1: (1.0, 0.6, "A2"), 2: (1.0, 0.9, "A2")})
    lines = ai_line(engine, line_my_profile="rank_15k", line_profile="rank_12k")
    assert lines == [["B2", "B2"]]  # The fake KataGo's human-like move is B2; the stones are settled after two moves.
    profiles = [
        q["overrideSettings"]["humanSLProfile"] for q in engine.queries if "humanSLProfile" in q["overrideSettings"]
    ]
    assert profiles == ["rank_15k", "rank_12k"]
    assert len(engine.queries) == 5  # The start, then a move and the areas, twice.


def ladder_run(engine, **play) -> tuple[FightRun, list]:
    """A fight in which white's stone at A1 (a setup stone) is to be captured by black, who plays first."""
    start = Position(9, 6.5, "japanese", (Move("W", (0, 0)),), (Move("W", (4, 4)),), "B")
    fight_run = FightRun(engine, replace(fight(), position=start), FightPlay(500, 0.04, **play))
    events = []
    fight_run.start(lambda: events.append("ready"), lambda message: events.append(("error", message)))
    return fight_run, events


LADDER = {0: (1.0, 0.6, "B1"), 1: (1.0, 0.9, "C3"), 2: (1.0, 0.9, "D3"), 3: (1.0, 0.9, "J9")}


def test_a_ladder_is_played_to_the_end():
    """Black's B1 ataris A1 and the areas are settled at once, but the stone is on the board: the fight goes on.

    White answers among the moves around the stone; the fight is judged when black has captured it (A2).
    """
    engine = FakeEngine(LADDER)
    fight_run, events = ladder_run(engine)
    user(fight_run, events, "B1")
    assert events[-1] == ("reply", "C3") and fight_run.outcome is None
    [restricted] = [query["allowMoves"] for query in engine.queries if "allowMoves" in query]
    assert restricted == [{"player": "W", "moves": ["A2", "A3", "B2"], "untilDepth": 1}]
    user(fight_run, events, "A2")
    assert events[-1][:2] == ("end", OUTCOME_WON)


def test_a_human_like_opponent_answers_a_chase_with_its_likeliest_local_move():
    """The fake human-like move is B2, which is one of the moves around A1."""
    fight_run, events = ladder_run(FakeEngine(LADDER), opponent=OPPONENT_RANK, profile="rank_15k")
    user(fight_run, events, "B1")
    assert events[-1] == ("reply", "B2")


def test_a_broken_chase_is_judged_as_usual():
    """After black's A3 the areas give the stones to white: the chase is broken, and the settled place is lost."""
    engine = FakeEngine({**LADDER, 3: (1.0, -0.9, "J9")})
    fight_run, events = ladder_run(engine)
    user(fight_run, events, "B1")
    user(fight_run, events, "A3")
    assert events[-1][:2] == ("end", OUTCOME_LOST)


def test_a_ladder_is_judged_at_the_most_moves_of_the_user(monkeypatch):
    monkeypatch.setattr("kentogo.quiz.fight_run.LADDER_USER_MOVES", 1)
    fight_run, events = ladder_run(FakeEngine(LADDER))
    user(fight_run, events, "B1")
    assert events[-1][:2] == ("end", OUTCOME_WON)


def strong_line(engine) -> list:
    fight_run, _events = run(engine)
    results = []
    fight_run.ask_strong_line(
        lambda _line: None,
        lambda line, end: results.append(([move.gtp() for move in line], end.reason)),
        lambda message: results.append(message),
    )
    return results


def test_the_sequence_of_the_strongest_ai_plays_katagos_best_moves():
    """Both sides play KataGo's best moves (B2, C2) until the stones are settled; no human-like query is made."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (1.0, 0.6, "C2"), 2: (1.0, 0.9, "J9")})
    assert strong_line(engine) == [(["B2", "C2"], "territory")]
    assert all("humanSLProfile" not in query["overrideSettings"] for query in engine.queries)


class BrokenEngine:
    def query(self, _request, callback):
        callback({"error": "broken"})
        return "x"


def test_the_sequence_of_the_ais_fails():
    assert ai_line(BrokenEngine()) == ["KataGo could not analyze the position: broken"]
