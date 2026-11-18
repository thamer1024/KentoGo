"""Tests for kentogo.quiz.fight_follow (the sequence of the AIs after a local fight, against a fake KataGo)."""

from test_fight_judge import fight

from kentogo.common.types import Move
from kentogo.quiz.fight_follow import DEFAULT_PROFILE, FollowLimits, FollowPlan, build_follow, follow_profiles
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


def follow(engine, points=None, limits=None) -> tuple[list[int], list[tuple[Move, ...]], list[str]]:
    """Make the sequence; return the lengths told by on_move, the sequences told by on_done, and the errors."""
    told, done, errors = [], [], []
    plan = FollowPlan(engine, fight(), STONES if points is None else points, PROFILES, 500, 0.04)
    build_follow(plan, lambda line: told.append(len(line)), done.append, errors.append, limits)
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
    times = iter([0.0, 5.0, 20.0])
    limits = FollowLimits(moves=60, seconds=10.0, clock=lambda: next(times))
    told, _done, _errors = follow(Engine(["A2", "B2", "C2"], {}), limits=limits)
    assert told == [1, 2]


def test_katago_cannot_answer():
    told, done, errors = follow(BrokenEngine())
    assert (told, done) == ([], []) and errors == ["KataGo could not analyze the position: broken"]


def test_the_profiles_of_the_two_sides():
    """A side without a rank plays at the other's rank; with neither, both play at 9d."""
    assert follow_profiles(PlayerRanks("15k", "12k")) == ("rank_15k", "rank_12k")
    assert follow_profiles(PlayerRanks("", "12k")) == ("rank_12k", "rank_12k")
    assert follow_profiles(PlayerRanks("15k", "")) == ("rank_15k", "rank_15k")
    assert follow_profiles(PlayerRanks()) == (DEFAULT_PROFILE, DEFAULT_PROFILE) == ("rank_9d", "rank_9d")
    assert follow_profiles(PlayerRanks("30k", "5d")) == ("rank_5d", "rank_5d")  # 30k is not a rank of the model.
