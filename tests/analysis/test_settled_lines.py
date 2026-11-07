"""Tests for kentogo.analysis.settled_lines (the sequences after a deep move until the place settles)."""

from pysgf import GoGame

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.game_analysis import EngineValues

GAME = "(;SZ[9]KM[0];B[ee];W[cc];B[gc])"  # Black's E5, white's C7, black's G7.
VALUES = EngineValues(max_visits=10, wide_root_noise=0.0)


class FakeEngine:
    """The areas change while the sequence is shorter than calm_after moves, then stay; KataGo's next move is near."""

    def __init__(self, calm_after: int = 7, next_move: str = "F6"):
        self.calm_after = calm_after
        self.next_move = next_move
        self.lengths = []

    def query(self, request, callback):
        moves = request["moves"]
        self.lengths.append(len(moves))
        level = min(len(moves), self.calm_after) / 10
        top = {"move": self.next_move, "order": 0, "visits": 10, "scoreLead": 0.0, "pv": [self.next_move, "D6", "F4"]}
        if "allowMoves" in request:
            point = request["allowMoves"][0]["moves"][0]
            top = {**top, "move": point, "pv": [point]}
        answer = {"id": "x", "rootInfo": {"scoreLead": -float(len(moves)), "winrate": 0.5, "visits": 10}}
        answer["moveInfos"] = [top]
        if request.get("includeOwnership", True):
            answer["ownership"] = [level] * 81
        callback(answer)
        return "x"


def analyzed(engine, **settings):
    root = GoGame.parse_sgf(GAME)
    targets = DeepTargets({"B": -100.0}, 10)  # Every black move is read deeply.
    game = analyze_game(engine, root, AnalysisSettings(**settings), VALUES, lambda *_: None, targets)
    return game, game.readings[id(game.nodes[3])]


def test_a_line_goes_on_until_the_areas_of_the_place_stay():
    game, readings = analyzed(FakeEngine(calm_after=7), settle_change=0.1)
    line = readings["played_line"]
    assert line["moves"][0] == "G7" and line["settled"] is True
    assert [step["length"] for step in line["steps"]] == [1, 3, 5, 7]  # 2 moves at a time; still from 5 to 7.
    assert len(line["end"]["ownership"]) == 81 and line["end"]["length"] == 7
    assert readings["best_line"]["moves"][0] == "F6"  # KataGo's best move, then its sequence.


def test_a_line_that_does_not_settle_stops_at_the_longest():
    _, readings = analyzed(FakeEngine(calm_after=100), settle_max_moves=6)
    line = readings["played_line"]
    assert line["settled"] is False and line["steps"][-1]["length"] == 6


def test_a_line_settles_when_the_players_leave_the_place():
    """KataGo's next move A1 is far from G7: the place is left as it is, at once."""
    _, readings = analyzed(FakeEngine(next_move="A1"), settle_radius=2)
    line = readings["played_line"]
    assert line["settled"] is True and [step["length"] for step in line["steps"]] == [1]


def test_the_first_reading_of_a_line_is_the_one_already_made():
    """The positions after the played move and after the best move were read already: a line starts after them."""
    _, readings = analyzed(FakeEngine(calm_after=3), settle_change=0.1)
    assert [step["length"] for step in readings["played_line"]["steps"]] == [1, 3]
    assert [step["length"] for step in readings["best_line"]["steps"]] == [1, 3]


def test_a_line_ends_before_a_move_of_the_sequence_that_leaves_the_place():
    """KataGo's next move F6 is near G7, but D6 after it is 3 points away: the line is G7 F6, then it ends."""
    _, readings = analyzed(FakeEngine(calm_after=100), settle_radius=2)
    line = readings["played_line"]
    assert line["moves"] == ["G7", "F6"] and line["settled"] is True
    assert [step["length"] for step in line["steps"]] == [1, 2]  # The end is read.


def test_without_the_areas_a_line_goes_on_while_the_players_stay():
    """By default the areas are not used (KataGo's areas already expect the sequence)."""
    _, readings = analyzed(FakeEngine(calm_after=3), settle_max_moves=6)
    assert [step["length"] for step in readings["played_line"]["steps"]] == [1, 3, 5, 6]
