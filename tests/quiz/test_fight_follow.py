"""Tests for kentogo.quiz.fight_follow (the sequence of the AIs after a local fight, against a fake KataGo)."""

from dataclasses import replace
from itertools import chain, repeat

from test_fight_judge import fight

from kentogo.common.types import Move, Position
from kentogo.katago.human_moves import most_likely_among
from kentogo.quiz.fight_follow import (
    DEFAULT_PROFILE,
    END_ALL,
    END_KILLED,
    END_LEFT,
    END_LENGTH,
    END_LIVED,
    END_LIVED_KILLED,
    END_MIXED,
    END_PASS,
    END_TERRITORY,
    END_TIME,
    FollowEnd,
    FollowLimits,
    FollowPlan,
    build_follow,
    build_strong_follow,
    follow_profiles,
    is_inconclusive,
    settled_end,
)
from kentogo.quiz.human_line import PlayerRanks

SIZE = 9
STONES = [(0, 0), (1, 0), (2, 0)]  # The judged points: black's stones A1, B1 and C1.
PROFILES = ("rank_15k", "rank_12k")


class Engine:
    """Answers the human-like queries with the next of the moves, and the others with the areas of the stones."""

    def __init__(self, moves: list[str], owners: dict[int, float]):
        self.moves = moves  # The human-like move after each number of moves (GTP points, or "pass").
        self.owners = owners  # The ownership of the stones after each number of moves (0 if not given).
        self.queries = []

    def query(self, request, callback):
        self.queries.append(request)
        count = len(request["moves"]) - 1  # The position has one move.
        callback({"isDuringSearch": True})
        if "humanSLProfile" in request["overrideSettings"]:
            callback({"rootInfo": {"scoreLead": 0.0}, "moveInfos": [], "humanPolicy": self._policy(self.moves[count])})
        else:
            callback({"rootInfo": {"scoreLead": 0.0}, "ownership": self._areas(self.owners.get(count, 0.0))})
        return "x"

    @staticmethod
    def _policy(point: str) -> list[float]:
        policy = [0.0] * (SIZE * SIZE + 1)
        if point == "pass":
            policy[SIZE * SIZE] = 1.0
        else:
            x, y = Move.from_gtp(point, "B").coord
            policy[(SIZE - 1 - y) * SIZE + x] = 1.0
        return policy

    @staticmethod
    def _areas(value: float) -> list[float]:
        values = [0.0] * (SIZE * SIZE)
        for x, y in STONES:
            values[(SIZE - 1 - y) * SIZE + x] = value
        return values

    def humans(self) -> list[str]:
        """The profiles of the human-like queries, in order."""
        return [
            q["overrideSettings"]["humanSLProfile"] for q in self.queries if "humanSLProfile" in q["overrideSettings"]
        ]


class BrokenEngine:
    def query(self, _request, callback):
        callback({"error": "broken"})
        return "x"


class StrongEngine:
    """Answers each query with the best move and the areas of the stones, by the number of moves after the position."""

    def __init__(self, moves: list[str], owners: dict[int, float], local: dict[int, str] | None = None, judged=None):
        self.moves = moves  # KataGo's best move after each number of moves (GTP points).
        self.owners = owners  # The ownership of the stones after each number of moves (0 if not given).
        self.local = local or {}  # The best move among the allowed ones (a query with "allowMoves"), by the same.
        self.judged = judged or STONES  # The points that have that ownership.
        self.queries = []

    def query(self, request, callback):
        self.queries.append(request)
        count = len(request["moves"]) - 1  # The position has one move.
        best = self.local[count] if "allowMoves" in request else self.moves[count]
        callback({"isDuringSearch": True})
        areas = [0.0] * (SIZE * SIZE)
        for x, y in self.judged:
            areas[(SIZE - 1 - y) * SIZE + x] = self.owners.get(count, 0.0)
        callback(
            {
                "rootInfo": {"scoreLead": 0.0},
                "moveInfos": [{"move": best, "order": 0, "pv": [best]}],
                "ownership": areas,
            }
        )
        return "x"


def run_follow(
    engine, points=None, limits=None, build=build_follow, problem=None
) -> tuple[list, list, list, list, list]:
    """Make the sequence; return what on_move, on_done (the sequences and the ends), on_error and the log were told.

    build is build_follow (the human-like sequence) or build_strong_follow (the strongest AI's); problem is the
    fight (fight() when not given).
    """
    told, done, ends, errors, logs = [], [], [], [], []
    plan = FollowPlan(
        engine, problem or fight(), STONES if points is None else points, PROFILES, 500, 0.04, logs.append
    )

    def on_done(line, end):
        done.append(line)
        ends.append(end)

    build(plan, lambda line: told.append(len(line)), on_done, errors.append, limits)
    return told, done, ends, errors, logs


def follow(engine, points=None, limits=None) -> tuple[list[int], list[tuple[Move, ...]], list[str]]:
    """Make the sequence; return the lengths told by on_move, the sequences told by on_done, and the errors."""
    told, done, _ends, errors, _logs = run_follow(engine, points, limits)
    return told, done, errors


def gtp(line: tuple[Move, ...]) -> list[str]:
    return [move.gtp() for move in line]


def test_the_sequence_goes_on_until_the_stones_are_settled():
    """Black A2, white B2, black C2: after that the stones are black's by 0.9, so the sequence ends."""
    engine = Engine(["A2", "B2", "C2", "D2"], {1: 0.3, 2: 0.5, 3: 0.9})
    told, done, errors = follow(engine)
    assert errors == [] and told == [1, 2, 3]  # Each move is told as it is made.
    assert [gtp(line) for line in done] == [["A2", "B2", "C2"]]
    assert engine.humans() == ["rank_15k", "rank_12k", "rank_15k"]  # The user's side first, then the opponent's.
    assert len(engine.queries) == 6  # A move and the areas, three times.


def test_the_opponent_plays_away_from_the_fight():
    """White plays J9, far from the fight: the sequence ends with that move, without asking for its areas."""
    engine = Engine(["A2", "J9", "C2"], {1: 0.3})
    told, done, _errors = follow(engine)
    assert told == [1, 2] and [gtp(line) for line in done] == [["A2", "J9"]]
    assert len(engine.queries) == 3  # A move and the areas, then a move.


def test_a_pass_ends_the_sequence():
    told, done, _errors = follow(Engine(["A2", "pass"], {1: 0.3}))
    assert told == [1, 2] and done[0][-1].is_pass


def test_without_points_to_judge_the_place_is_never_settled():
    """Only the limits of the moves end the sequence."""
    told, done, _errors = follow(Engine(["A2", "B2", "C2"], {1: 0.9, 2: 0.9}), points=[], limits=FollowLimits(moves=3))
    assert told == [1, 2, 3] and len(done[0]) == 3


def test_the_time_limit():
    """The time is up after the second move (the clock is read at the start and after each move)."""
    times = chain([0.0, 5.0, 20.0], repeat(20.0))  # Then the clock stays (it is read again when the end is logged).
    limits = FollowLimits(moves=60, seconds=10.0, clock=lambda: next(times))
    told, _done, _errors = follow(Engine(["A2", "B2", "C2"], {}), limits=limits)
    assert told == [1, 2]


def test_katago_cannot_answer():
    told, done, errors = follow(BrokenEngine())
    assert (told, done) == ([], []) and errors == ["KataGo could not analyze the position: broken"]


def test_the_end_when_the_place_is_settled():
    """No stone of the judged points is on the board at the start, so black owning them is territory."""
    engine = Engine(["A2", "B2", "C2", "D2"], {1: 0.3, 2: 0.5, 3: 0.9})
    _told, _done, ends, _errors, _logs = run_follow(engine)
    assert ends == [FollowEnd(END_TERRITORY, "B")]


def test_the_end_when_a_side_leaves_or_passes():
    _told, _done, ends, _errors, _logs = run_follow(Engine(["A2", "J9"], {1: 0.3}))
    assert ends == [FollowEnd(END_LEFT)]
    _told, _done, ends, _errors, _logs = run_follow(Engine(["A2", "pass"], {1: 0.3}))
    assert ends == [FollowEnd(END_PASS)]


def test_the_end_at_the_most_moves_and_at_the_time_limit():
    engine = Engine(["A2", "B2", "C2"], {})
    _told, _done, ends, _errors, _logs = run_follow(engine, limits=FollowLimits(moves=2))
    assert ends == [FollowEnd(END_LENGTH)]
    times = chain([0.0, 20.0], repeat(20.0))
    limits = FollowLimits(moves=60, seconds=10.0, clock=lambda: next(times))
    _told, _done, ends, _errors, _logs = run_follow(engine, limits=limits)
    assert ends == [FollowEnd(END_TIME)]


def test_the_end_is_logged():
    _told, _done, _ends, _errors, logs = run_follow(Engine(["A2", "J9"], {1: 0.3}))
    [record] = logs
    assert {key: record[key] for key in ("line", "event", "moves", "reason", "color")} == {
        "line": "ai_follow",
        "event": "ai_follow_end",
        "moves": 2,
        "reason": END_LEFT,
        "color": None,
    }
    assert isinstance(record["seconds"], float)


def test_the_error_is_logged():
    _told, _done, _ends, errors, logs = run_follow(BrokenEngine())
    message = "KataGo could not analyze the position: broken"
    assert errors == [message]
    assert logs == [{"line": "ai_follow", "event": "ai_follow_error", "moves": 0, "message": message}]


def test_the_strongest_ai_goes_on_until_the_stones_are_settled():
    """Black plays A2, white B2, black C2 (KataGo's best); then the stones are black's by 0.9, so it ends."""
    engine = StrongEngine(["A2", "B2", "C2", "D2"], {3: 0.9})
    told, done, ends, errors, _logs = run_follow(engine, build=build_strong_follow)
    assert errors == [] and told == [1, 2, 3]
    assert [gtp(line) for line in done] == [["A2", "B2", "C2"]] and ends == [FollowEnd(END_TERRITORY, "B")]
    assert [move.color for move in done[0]] == ["B", "W", "B"]  # The user's side first.
    assert len(engine.queries) == 4  # One answer has the best move and the areas: a query for each position.
    assert all("humanSLProfile" not in query["overrideSettings"] for query in engine.queries)


def dead_stone_fight():
    """White's stone at A1 (and one at E5) at the start, black to play: the judged point A1 is to be captured."""
    start = Position(SIZE, 6.5, "japanese", (Move("W", (0, 0)),), (Move("W", (4, 4)),), "B")
    return replace(fight(), position=start)


def test_the_strongest_ai_goes_on_until_the_dead_stone_is_captured():
    """Black ataris A1 (B1); the areas then say that A1 is dead, but it is on the board: the sequence goes on.

    Both sides choose only among the moves around the stone: white plays elsewhere (C3), and black captures (A2).
    """
    engine = StrongEngine(["B1", "D9", "D9", "D9"], {1: 0.9, 2: 0.9, 3: 0.9}, local={1: "C3", 2: "A2"})
    told, done, ends, errors, _logs = run_follow(
        engine, points=[(0, 0)], build=build_strong_follow, problem=dead_stone_fight()
    )
    assert errors == [] and told == [1, 2, 3] and [gtp(line) for line in done] == [["B1", "C3", "A2"]]
    assert ends == [FollowEnd(END_KILLED, "B")]
    restricted = [query["allowMoves"] for query in engine.queries if "allowMoves" in query]
    assert restricted == [
        [{"player": "W", "moves": ["A2", "A3", "B2"], "untilDepth": 1}],
        [{"player": "B", "moves": ["A2", "A3", "B2"], "untilDepth": 1}],
    ]


def running_fight():
    """White's E5 has two liberties (D5 and E6): black's E4 and F5 are next to it."""
    start = Position(SIZE, 6.5, "japanese", (Move("B", (4, 3)), Move("B", (5, 4))), (Move("W", (4, 4)),), "B")
    return replace(fight(), position=start)


def test_the_chase_goes_on_when_the_group_gets_more_liberties():
    """After D5 and E6 white has three liberties, but the areas still give the group to black."""
    engine = StrongEngine(["D5"] + ["D9"] * 3, {1: 0.9, 2: 0.9}, {1: "E6", 2: "E7"}, [(4, 4), (4, 5)])
    _told, done, ends, _errors, logs = run_follow(
        engine, [(4, 4)], FollowLimits(chase_moves=3), build_strong_follow, running_fight()
    )
    assert [gtp(line) for line in done] == [["D5", "E6", "E7"]] and ends == [FollowEnd(END_LENGTH)]
    assert sum("allowMoves" in query for query in engine.queries) == 2 and logs[-1]["chase"] == "going"
    assert logs[-1]["chase_share"] == 0.9


def test_a_broken_chase_goes_back_to_the_normal_end():
    """After E6 the areas give the group to white: the chase is broken, and the settled place ends the sequence."""
    engine = StrongEngine(["D5"] + ["D9"] * 3, {1: 0.9, 2: -0.9}, {1: "E6", 2: "E7"}, [(4, 4), (4, 5)])
    _told, done, ends, _errors, logs = run_follow(engine, [(4, 4)], None, build_strong_follow, running_fight())
    assert [gtp(line) for line in done] == [["D5", "E6"]] and ends == [FollowEnd(END_LIVED, "W")]
    assert logs[-1]["chase"] == "broken"


def test_the_human_like_sequence_plays_the_chase_to_the_end():
    """The areas are settled after B1, but both sides go on around A1 until black captures it."""
    engine = Engine(["B1", "A3", "A2"], {1: 0.9, 2: 0.9, 3: 0.9})
    told, done, ends, _errors, logs = run_follow(engine, points=[(0, 0)], problem=dead_stone_fight())
    assert told == [1, 2, 3] and [gtp(line) for line in done] == [["B1", "A3", "A2"]]
    assert ends == [FollowEnd(END_KILLED, "B")] and logs[-1]["chase"] == "captured"


def test_the_most_likely_move_among_some_points():
    answer = {"humanPolicy": Engine._policy("C3")}
    assert most_likely_among(answer, SIZE, "B", ["A2", "C3"]) == Move.from_gtp("C3", "B")


def test_a_dead_stone_with_room_does_not_make_the_strongest_ai_go_on():
    """White's C1 (three liberties) is dead by the areas, but it cannot be ataried: the sequence ends when settled."""
    start = Position(SIZE, 6.5, "japanese", (Move("W", (2, 0)),), (Move("W", (4, 4)),), "B")
    engine = StrongEngine(["E4", "D9"], {1: 0.9})
    _told, done, ends, _errors, _logs = run_follow(
        engine, points=[(2, 0)], build=build_strong_follow, problem=replace(fight(), position=start)
    )
    assert [gtp(line) for line in done] == [["E4"]] and ends == [FollowEnd(END_KILLED, "B")]
    assert not any("allowMoves" in query for query in engine.queries)


def test_the_strongest_ai_ends_at_once_when_no_dead_stone_is_on_the_board():
    """The judged point has no stone at the start (territory), so nothing is to be captured."""
    engine = StrongEngine(["A2", "B2", "C2", "D2"], {3: 0.9})
    run_follow(engine, build=build_strong_follow)
    assert not any("allowMoves" in query for query in engine.queries)


def test_the_strongest_ai_ends_like_the_human_like_sequence():
    """Away from the fight, at the most moves, and when KataGo cannot answer."""
    _told, _done, ends, _errors, _logs = run_follow(StrongEngine(["A2", "J9"], {}), build=build_strong_follow)
    assert ends == [FollowEnd(END_LEFT)]
    engine, limits = StrongEngine(["A2", "B2", "C2"], {}), FollowLimits(moves=2)
    _told, _done, ends, _errors, _logs = run_follow(engine, limits=limits, build=build_strong_follow)
    assert ends == [FollowEnd(END_LENGTH)]
    told, done, ends, errors, _logs = run_follow(BrokenEngine(), build=build_strong_follow)
    assert (told, done, ends) == ([], [], []) and len(errors) == 1


def test_the_strongest_ai_is_logged_as_its_own_line():
    _told, _done, _ends, _errors, logs = run_follow(StrongEngine(["A2", "J9"], {}), build=build_strong_follow)
    [record] = logs
    assert (record["line"], record["event"], record["reason"]) == ("strong_follow", "strong_follow_end", END_LEFT)
    _told, _done, _ends, errors, logs = run_follow(BrokenEngine(), build=build_strong_follow)
    assert len(errors) == 1 and [(r["line"], r["event"]) for r in logs] == [("strong_follow", "strong_follow_error")]


def test_only_some_ends_are_inconclusive():
    """No conclusion: the points ended in different ways, or the sequence was cut by the moves or by the time."""
    assert all(is_inconclusive(FollowEnd(reason)) for reason in (END_MIXED, END_LENGTH, END_TIME))
    conclusive = (END_LIVED, END_KILLED, END_TERRITORY, END_LIVED_KILLED, END_ALL, END_LEFT, END_PASS)
    assert not any(is_inconclusive(FollowEnd(reason)) for reason in conclusive)


def stones_fight():
    """A fight in which black has a stone at A1, white at E5, and the points A1, E5 and C3 (empty) are judged."""
    start = Position(SIZE, 6.5, "japanese", (Move("B", (0, 0)), Move("W", (4, 4))), (), "B")
    return replace(fight(), position=start)


def test_a_stone_that_stays_has_lived_and_one_that_is_gone_was_killed():
    assert settled_end(stones_fight(), {(0, 0): 0.9}, [(0, 0)]) == FollowEnd(END_LIVED, "B")
    assert settled_end(stones_fight(), {(0, 0): -0.9}, [(0, 0)]) == FollowEnd(END_KILLED, "W")
    assert settled_end(stones_fight(), {(2, 2): 0.9}, [(2, 2)]) == FollowEnd(END_TERRITORY, "B")


def test_one_side_owning_all_the_points_is_a_conclusion():
    """Black's stone A1 lives and white's stone E5 is captured: black lives and kills; with territory it is all."""
    areas = {(0, 0): 0.9, (4, 4): 0.9, (2, 2): 0.9}
    assert settled_end(stones_fight(), areas, [(0, 0), (4, 4)]) == FollowEnd(END_LIVED_KILLED, "B")
    assert settled_end(stones_fight(), areas, [(4, 4), (2, 2)]) == FollowEnd(END_ALL, "B")


def test_points_that_end_in_different_ways_are_counted():
    """Black's stone lives and white's stone lives, and black owns the empty point: three points, two of black's."""
    areas = {(0, 0): 0.9, (4, 4): -0.9, (2, 2): 0.9}
    end = settled_end(stones_fight(), areas, [(0, 0), (4, 4), (2, 2)])
    assert end == FollowEnd(END_MIXED, None, 2, 1)


def test_the_profiles_of_the_two_sides():
    """A side without a rank plays at the other's rank; with neither, both play at 9d."""
    assert follow_profiles(PlayerRanks("15k", "12k")) == ("rank_15k", "rank_12k")
    assert follow_profiles(PlayerRanks("", "12k")) == ("rank_12k", "rank_12k")
    assert follow_profiles(PlayerRanks("15k", "")) == ("rank_15k", "rank_15k")
    assert follow_profiles(PlayerRanks()) == (DEFAULT_PROFILE, DEFAULT_PROFILE) == ("rank_9d", "rank_9d")
    assert follow_profiles(PlayerRanks("30k", "5d")) == ("rank_5d", "rank_5d")  # 30k is not a rank of the model.
