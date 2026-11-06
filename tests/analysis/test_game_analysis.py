"""Tests for kentogo.analysis.analyze, game_analysis, node_analysis and query (the analysis of a game)."""

from dataclasses import replace

from pysgf import GoGame

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.game_analysis import EngineValues
from kentogo.analysis.node_analysis import ADDITIONAL_MOVE_ORDER, apply_answer, empty_analysis, update_move_analysis
from kentogo.analysis.played_moves import played_move_loss
from kentogo.analysis.query import QuerySettings, node_query
from kentogo.record.katrain_kt import encode_kt

# Black's move 3 has two branches: A5 loses 5.5 points, D2 is fine.
GAME = "(;SZ[5]KM[0.5]RU[Chinese];B[cc];W[bb](;B[aa])(;B[db]))"
SCORES = {(): 0.0, ("C3",): 1.0, ("C3", "B4"): 0.5, ("C3", "B4", "A5"): -5.0, ("C3", "B4", "D4"): 0.6}
# KentoGo's readings around A5 (see analysis.kentogo_reading): passing costs black 3.5 points, white can
# leave A5 (passing after it costs nothing), but not the best move E5 (passing after it costs 3.5 points).
READINGS = {
    ("C3", "B4", "pass"): -3.0,
    ("C3", "B4", "E5"): 0.5,
    ("C3", "B4", "A5", "pass"): -5.0,
    ("C3", "B4", "E5", "pass"): 4.0,
}
VALUES = EngineValues(max_visits=500, wide_root_noise=0.04)


class FakeEngine:
    """Answers each query at once with a score that depends on the moves (as KataGo's final answer)."""

    def __init__(self, failing: tuple[str, ...] | None = None, times: int = 1000):
        self.queries = []
        self.failing = failing
        self.times = times  # How many times the failing position fails.

    def query(self, request, callback):
        self.queries.append(request)
        moves = tuple(point for _, point in request["moves"])
        if moves == self.failing and self.times > 0:
            self.times -= 1
            callback({"id": "x", "error": "broken"})
            return "x"
        if "allowMoves" in request:  # Only the played move: read in the position before it, 1 point worse for black.
            point = request["allowMoves"][0]["moves"][0]
            score = SCORES[(*moves, point)] - 1.0
        else:
            point, score = "E5", {**SCORES, **READINGS}[moves]
        candidate = {"move": point, "order": 0, "visits": request["maxVisits"], "scoreLead": score, "pv": [point, "A1"]}
        callback({"id": "x", "isDuringSearch": True, "rootInfo": {}, "moveInfos": []})  # Not used.
        callback(
            {
                "id": "x",
                "rootInfo": {"scoreLead": score, "winrate": 0.5, "visits": request["maxVisits"]},
                "moveInfos": [candidate],
                "policy": [0.04] * 26,
                **({"ownership": [0.0] * 25} if request.get("includeOwnership", True) else {}),
            }
        )
        return "x"


def root() -> object:
    return GoGame.parse_sgf(GAME)


def by_moves(engine: FakeEngine) -> dict[tuple, dict]:
    return {tuple(point for _, point in query["moves"]): query for query in analyses(engine)}


def by_moves_of(query: dict) -> tuple:
    return tuple(point for _, point in query["moves"])


def analyses(engine: FakeEngine) -> list[dict]:
    """The queries that analyze positions (not the played moves)."""
    return [query for query in engine.queries if "allowMoves" not in query]


def played(engine: FakeEngine) -> list[dict]:
    """The queries that read only the played move."""
    return [query for query in engine.queries if "allowMoves" in query]


def test_every_node_is_analyzed_with_katrains_query():
    engine = FakeEngine()
    steps = []
    game = analyze_game(engine, root(), AnalysisSettings(), VALUES, lambda *step: steps.append(step))
    queries = by_moves(engine)
    assert set(queries) == set(SCORES)  # The branches too.
    query = queries[("C3", "B4", "A5")]
    assert (query["maxVisits"], query["priority"], query["rules"], query["komi"]) == (500, -100, "chinese", 0.5)
    assert query["overrideSettings"] == {"reportAnalysisWinratesAs": "BLACK", "wideRootNoise": 0.04}  # No time limit.
    assert (query["includePolicy"], query["includeOwnership"], query["analyzeTurns"]) == (True, True, [3])
    assert ("first", 5, 5) in steps and steps[-1] == ("played", 4, 4)
    mistake = game.nodes[3]
    assert "pv" not in game.analysis(mistake)["root"]  # The answer is kept in its own node only.


def test_fast_visits():
    engine = FakeEngine()
    analyze_game(engine, root(), AnalysisSettings(fast=True, fast_visits=8), VALUES, lambda *_: None)
    assert {query["maxVisits"] for query in engine.queries} == {8}  # The played moves too.


def test_saved_analysis_data_is_used_as_it_is():
    """A node with analysis data (KT) is not analyzed again, as in KaTrain."""
    saved = {"moves": {}, "root": {"scoreLead": 1.0, "winrate": 0.5, "visits": 9}, "completed": True}
    text = GAME.replace(";B[cc]", ";B[cc]KT[" + "][".join(encode_kt(saved)) + "]")
    engine = FakeEngine()
    game = analyze_game(engine, GoGame.parse_sgf(text), AnalysisSettings(), VALUES, lambda *_: None)
    assert ("C3",) not in by_moves(engine) and len(analyses(engine)) == 4
    assert game.analysis(game.nodes[1])["root"]["visits"] == 9


def test_reanalysis_of_the_mistakes_only():
    """The node of the mistake and the node before it (its child lost points) are analyzed again."""
    engine = FakeEngine()
    settings = AnalysisSettings(reanalyze=True, mistakes_only=True)
    steps = []
    analyze_game(engine, root(), settings, VALUES, lambda *step: steps.append(step))
    again = analyses(engine)[5:]
    assert sorted(len(query["moves"]) for query in again) == [2, 3]
    assert {query["maxVisits"] for query in again} == {1000}  # The fewest visits (500) plus max_visits.
    assert {query["priority"] for query in again} == {-1_000_000}
    assert ("again", 2, 2) in steps


def test_a_failed_query_is_asked_again_and_the_others_are_kept():
    """A failed node is asked again (retries times), and the nodes that still fail are kept."""
    once = FakeEngine(failing=("C3", "B4"), times=1)
    assert analyze_game(once, root(), AnalysisSettings(), VALUES, lambda *_: None).failed == 0
    assert len(analyses(once)) == 6
    always = FakeEngine(failing=("C3", "B4"))
    game = analyze_game(always, root(), AnalysisSettings(retries=2), VALUES, lambda *_: None)
    assert [node.depth for node in game.failed_nodes] == [2] and len(analyses(always)) == 7
    assert game.analysis(game.nodes[2]) is None and game.analysis(game.nodes[3]) is not None


def test_update_move_analysis_keeps_the_smaller_order_and_the_values_of_more_visits():
    analysis = empty_analysis()
    update_move_analysis(analysis, {"order": 1, "visits": 10, "scoreLead": 1.0}, "C3")
    update_move_analysis(analysis, {"visits": 5, "scoreLead": 9.0, "prior": 0.2}, "C3")  # Fewer visits.
    assert analysis["moves"]["C3"] == {"move": "C3", "order": 1, "visits": 10, "scoreLead": 1.0, "prior": 0.2}
    update_move_analysis(analysis, {"order": 0, "visits": 20, "scoreLead": 2.0}, "C3")
    assert analysis["moves"]["C3"]["scoreLead"] == 2.0 and analysis["moves"]["C3"]["order"] == 0


def test_a_new_answer_puts_the_old_moves_at_the_end():
    analysis = empty_analysis()
    update_move_analysis(analysis, {"order": 0, "visits": 10, "scoreLead": 1.0}, "A1")
    apply_answer(analysis, {"rootInfo": {"scoreLead": 0.0}, "moveInfos": []})
    assert analysis["moves"]["A1"]["order"] == ADDITIONAL_MOVE_ORDER and analysis["completed"] is True


def test_no_query_when_stones_are_removed():
    node = GoGame.parse_sgf("(;SZ[5];B[cc];AE[cc];W[dd])").nodes_in_tree[-1]
    assert node_query(node, QuerySettings(10, 0.0, 0)) is None


def test_query_with_placed_stones():
    node = GoGame.parse_sgf("(;SZ[5]AB[aa][bb]PL[W];W[cc])").nodes_in_tree[-1]
    query = node_query(node, QuerySettings(10, 0.0, 0))
    assert query["initialStones"] == [["B", "A5"], ["B", "B4"]]
    assert (query["initialPlayer"], query["moves"], query["rules"]) == ("W", [["W", "C3"]], "japanese")


def test_mistakes_are_analyzed_again_from_the_threshold():
    """A loss of exactly reanalyze_threshold counts ("or more")."""
    settings = AnalysisSettings(reanalyze=True, mistakes_only=True, reanalyze_threshold=5.5)
    engine = FakeEngine()
    analyze_game(engine, root(), settings, VALUES, lambda *_: None)
    assert sorted(len(query["moves"]) for query in analyses(engine)[5:]) == [2, 3]
    high = FakeEngine()
    analyze_game(high, root(), replace(settings, reanalyze_threshold=5.6), VALUES, lambda *_: None)
    assert analyses(high)[5:] == []


def test_the_range_covers_the_positions_of_its_moves():
    """Move 2 needs the positions after moves 1 and 2; the ends may be given in any order."""
    engine = FakeEngine()
    settings = AnalysisSettings(reanalyze=True, reanalyze_visits=50, move_from=2, move_to=2)
    analyze_game(engine, root(), settings, VALUES, lambda *_: None)
    assert sorted(len(query["moves"]) for query in analyses(engine)[5:]) == [1, 2]
    reversed_range = FakeEngine()
    settings = AnalysisSettings(reanalyze=True, reanalyze_visits=50, move_from=3, move_to=2)
    analyze_game(reversed_range, root(), settings, VALUES, lambda *_: None)
    assert sorted(len(query["moves"]) for query in analyses(reversed_range)[5:]) == [1, 2, 3, 3]


def test_reanalysis_counts_the_visits_of_saved_data():
    """Saved analysis data counts with its visits (KaTrain counts it as 0, so it would not read more deeply)."""
    saved = {"moves": {}, "root": {"scoreLead": 1.0, "winrate": 0.5, "visits": 900}, "completed": True}
    text = GAME.replace(";B[cc]", ";B[cc]KT[" + "][".join(encode_kt(saved)) + "]")
    engine = FakeEngine()
    analyze_game(engine, GoGame.parse_sgf(text), AnalysisSettings(reanalyze=True), VALUES, lambda *_: None)
    assert {query["maxVisits"] for query in analyses(engine)[4:]} == {1000}  # The fewest: 500 asked.


def test_each_played_move_is_read_in_the_position_before_it():
    """The played move is read with only it allowed, as deeply as the position."""
    engine = FakeEngine()
    game = analyze_game(engine, root(), AnalysisSettings(), VALUES, lambda *_: None)
    queries = played(engine)
    assert sorted(len(query["moves"]) for query in queries) == [0, 1, 2, 2]  # The position before each move.
    assert {query["maxVisits"] for query in queries} == {500}
    assert queries[0]["allowMoves"][0]["untilDepth"] == 1 and not queries[0]["includeOwnership"]
    mistake = game.nodes[3]
    assert game.points_lost(mistake) == 5.5  # KaTrain's: the score before minus the score after.
    assert played_move_loss(game, mistake) == 6.5  # KentoGo's: inside the position before the move.
    assert game.analysis(mistake.parent)["moves"]["A5"]["order"] == ADDITIONAL_MOVE_ORDER


def test_a_played_move_read_well_enough_is_not_read_again():
    """When KataGo's analysis of the position already read the played move well, its value is used."""

    class KnowsA5(FakeEngine):
        def query(self, request, callback):
            moves = tuple(point for _, point in request["moves"])
            if moves == ("C3", "B4") and "allowMoves" not in request:
                self.queries.append(request)
                a5 = {"move": "A5", "order": 1, "visits": 100, "scoreLead": -4.0, "pv": ["A5"]}
                e5 = {"move": "E5", "order": 0, "visits": 400, "scoreLead": 0.5, "pv": ["E5"]}
                callback({"id": "x", "rootInfo": {"scoreLead": 0.5, "visits": 500}, "moveInfos": [e5, a5]})
                return "x"
            return super().query(request, callback)

    engine = KnowsA5()
    game = analyze_game(engine, root(), AnalysisSettings(), VALUES, lambda *_: None)
    assert [query["allowMoves"][0]["moves"] for query in played(engine)] == [["C3"], ["B4"], ["D4"]]  # Not A5.
    assert played_move_loss(game, game.nodes[3]) == 4.5


def test_saved_data_of_katrain_is_read_again():
    """Without KGM[KentoGo], a saved played move's value is from the position after it, so it is read again."""
    saved = {"moves": {"B4": {"move": "B4", "order": 999, "visits": 500, "scoreLead": 0.5}}, "completed": True}
    saved["root"] = {"scoreLead": 1.0, "winrate": 0.5, "visits": 500}
    text = GAME.replace(";B[cc]", ";B[cc]KT[" + "][".join(encode_kt(saved)) + "]")
    for mark, expected in (("", 4), ("KGM[KentoGo]", 3)):
        engine = FakeEngine()
        game_text = text.replace("RU[Chinese]", "RU[Chinese]" + mark)
        analyze_game(engine, GoGame.parse_sgf(game_text), AnalysisSettings(), VALUES, lambda *_: None)
        assert len(played(engine)) == expected


def test_moves_that_can_become_problems_are_read_deeply():
    """Black's A5 lost 6.5 points: the positions before and after it, and A5 itself, are read with the deep visits."""
    engine = FakeEngine()
    targets = DeepTargets({"B": 5.0, "W": 1.0}, 2000)
    steps = []
    game = analyze_game(engine, root(), AnalysisSettings(), VALUES, lambda *step: steps.append(step), targets)
    deep = [query for query in engine.queries if query["maxVisits"] == 2000]
    positions = [query for query in deep if "allowMoves" not in query and by_moves_of(query) in SCORES]
    assert sorted(len(query["moves"]) for query in positions) == [2, 3]  # Not KentoGo's readings.
    assert [query["allowMoves"][0]["moves"] for query in deep if "allowMoves" in query] == [["A5"]]
    assert [node.depth for node in game.deep_nodes] == [3] and game.deep_visits == 2000  # White gained.
    assert ("deep", 2, 2) in steps
    assert played_move_loss(game, game.nodes[3]) == 6.5


def test_a_move_that_loses_less_when_read_deeply_is_not_kept():
    class DeeperIsBetter(FakeEngine):
        def query(self, request, callback):
            moves = tuple(point for _, point in request["moves"])
            if request["maxVisits"] == 2000 and "allowMoves" in request and moves == ("C3", "B4"):
                self.queries.append(request)
                a5 = {"move": "A5", "order": 0, "visits": 2000, "scoreLead": 0.0, "pv": ["A5"]}
                callback({"id": "x", "rootInfo": {"scoreLead": 0.0, "visits": 2000}, "moveInfos": [a5]})
                return "x"
            return super().query(request, callback)

    game = analyze_game(
        DeeperIsBetter(), root(), AnalysisSettings(), VALUES, lambda *_: None, DeepTargets({"B": 5}, 2000)
    )
    assert game.deep_nodes == []


def test_no_deep_reading_without_targets_or_for_a_color_not_given():
    engine = FakeEngine()
    assert analyze_game(engine, root(), AnalysisSettings(), VALUES, lambda *_: None).deep_nodes == []
    game = analyze_game(FakeEngine(), root(), AnalysisSettings(), VALUES, lambda *_: None, DeepTargets({"W": 0}, 900))
    assert [node.move.player for node in game.deep_nodes] == []  # White's B4 gained 1.5 points (a loss below 0).


def test_a_move_in_a_decided_position_is_not_read_deeply():
    """The quiz does not ask moves of a decided game first, so they are not read deeply either."""
    decided = DeepTargets({"B": 5.0}, 2000, lambda winrate, lead: lead is not None and lead > 0.4)
    game = analyze_game(FakeEngine(), root(), AnalysisSettings(), VALUES, lambda *_: None, decided)
    assert game.deep_nodes == []  # Before A5, black led by 0.5 points: decided by this rule.
    open_game = DeepTargets({"B": 5.0}, 2000, lambda winrate, lead: lead is not None and lead > 0.6)
    assert [
        node.depth
        for node in analyze_game(
            FakeEngine(), root(), AnalysisSettings(), VALUES, lambda *_: None, open_game
        ).deep_nodes
    ] == [3]


def test_kentogo_readings_of_a_deep_move():
    """The tenuki readings of A5 are kept with KataGo's values, from black's side, with the deep visits."""
    engine = FakeEngine()
    steps = []
    game = analyze_game(
        engine, root(), AnalysisSettings(), VALUES, lambda *step: steps.append(step), DeepTargets({"B": 5}, 2000)
    )
    readings = game.readings[id(game.nodes[3])]
    assert set(readings) == {"pass_before", "pass_after_played", "best_after", "pass_after_best"}
    assert readings["pass_before"]["scoreLead"] == -3.0 and readings["pass_before"]["next"] == "E5"
    assert readings["pass_after_played"]["scoreLead"] == -5.0  # White can leave A5: it threatens nothing.
    assert readings["pass_after_best"]["scoreLead"] == 4.0  # White cannot leave E5.
    assert len(readings["best_after"]["ownership"]) == 25 and "ownership" not in readings["pass_before"]
    tenuki = [query for query in engine.queries if by_moves_of(query) in READINGS]
    assert len(tenuki) == 4 and {query["maxVisits"] for query in tenuki} == {2000}
    assert ("tenuki", 1, 4) in steps and steps[-1] == ("tenuki", 4, 4)  # One count for all the readings.
