"""Tests for kentogo.quiz.fight_run (a local fight played against a fake KataGo)."""

from test_fight_judge import fight

from kentogo.common.types import Move
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


def test_the_strongest_opponent_leaves_before_it_is_settled():
    """KataGo answers far away: black's move did not need an answer, so it is wrong."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (1.0, 0.6, "J9")})
    fight_run, events = run(engine)
    user(fight_run, events, "A2")
    assert events[-1] == ("end", OUTCOME_OPPONENT_LEFT, 0.0)


def test_the_stones_die():
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (-9.0, -0.9, "B2")})
    fight_run, events = run(engine)
    user(fight_run, events, "A2")
    assert events[-1] == ("end", OUTCOME_LOST, 10.0) and not fight_run.outcome.correct


def test_a_human_like_opponent():
    """With the opponent's rank, white plays the human-like move (B2), asked with the profile."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (1.0, 0.6, "J9")})
    fight_run, events = run(engine, opponent=OPPONENT_RANK, profile="rank_15k")
    user(fight_run, events, "A2")
    assert events[-1] == ("reply", "B2")
    assert engine.queries[-1]["overrideSettings"]["humanSLProfile"] == "rank_15k"


def ai_line(engine, **play) -> list:
    fight_run, _events = run(engine, **play)
    lines = []
    fight_run.ask_ai_line(
        lambda line: lines.append([move.gtp() for move in line]), lambda message: lines.append(message)
    )
    return lines


def test_the_sequence_of_the_strongest_ais():
    """Both sides play KataGo's best moves, as long as the game's sequence of the fight (3 moves)."""
    engine = FakeEngine({0: (1.0, 0.6, "A2"), 1: (1.0, 0.6, "B2"), 2: (1.0, 0.6, "C2")})
    assert ai_line(engine) == [["A2", "B2", "C2"]]


def test_the_sequence_of_the_human_like_ais():
    """With the opponent's rank, both sides play the human-like moves of their own ranks."""
    engine = FakeEngine({0: (1.0, 0.6, "A2"), 1: (1.0, 0.6, "B2"), 2: (1.0, 0.6, "C2")})
    lines = ai_line(engine, opponent=OPPONENT_RANK, profile="rank_12k", my_profile="rank_15k")
    assert lines[0][0] == "B2"
    profiles = [query["overrideSettings"]["humanSLProfile"] for query in engine.queries[1:3]]
    assert profiles == ["rank_15k", "rank_12k"]


class BrokenEngine:
    def query(self, _request, callback):
        callback({"error": "broken"})
        return "x"


def test_the_sequence_of_the_ais_fails():
    assert ai_line(BrokenEngine()) == ["KataGo could not analyze the position: broken"]
