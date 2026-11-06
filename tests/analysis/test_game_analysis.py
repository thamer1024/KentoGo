"""Tests for kentogo.analysis.game_analysis, node_analysis and query (KaTrain's analysis of a game)."""

from pysgf import GoGame

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.game_analysis import EngineValues, analyze_game
from kentogo.analysis.node_analysis import ADDITIONAL_MOVE_ORDER, apply_answer, empty_analysis, update_move_analysis
from kentogo.analysis.query import QuerySettings, node_query
from kentogo.record.katrain_kt import encode_kt

# Black's move 3 has two branches: A5 loses 5.5 points, D2 is fine.
GAME = "(;SZ[5]KM[0.5]RU[Chinese];B[cc];W[bb](;B[aa])(;B[db]))"
SCORES = {(): 0.0, ("C3",): 1.0, ("C3", "B4"): 0.5, ("C3", "B4", "A5"): -5.0, ("C3", "B4", "D4"): 0.6}
VALUES = EngineValues(max_visits=500, wide_root_noise=0.04)


class FakeEngine:
    """Answers each query at once with a score that depends on the moves (as KataGo's final answer)."""

    def __init__(self, failing: tuple[str, ...] | None = None):
        self.queries = []
        self.failing = failing

    def query(self, request, callback):
        self.queries.append(request)
        moves = tuple(point for _, point in request["moves"])
        if moves == self.failing:
            callback({"id": "x", "error": "broken"})
            return "x"
        score = SCORES[moves]
        candidate = {"move": "E5", "order": 0, "visits": request["maxVisits"], "scoreLead": score, "pv": ["E5", "A1"]}
        callback({"id": "x", "isDuringSearch": True, "rootInfo": {}, "moveInfos": []})  # Not used.
        callback(
            {
                "id": "x",
                "rootInfo": {"scoreLead": score, "winrate": 0.5, "visits": request["maxVisits"]},
                "moveInfos": [candidate],
                "policy": [0.04] * 26,
                "ownership": [0.0] * 25,
            }
        )
        return "x"


def root() -> object:
    return GoGame.parse_sgf(GAME)


def by_moves(engine: FakeEngine) -> dict[tuple, dict]:
    return {tuple(point for _, point in query["moves"]): query for query in engine.queries}


def test_every_node_is_analyzed_with_katrains_query():
    engine = FakeEngine()
    steps = []
    game = analyze_game(engine, root(), AnalysisSettings(max_time=30.0), VALUES, lambda *step: steps.append(step))
    queries = by_moves(engine)
    assert set(queries) == set(SCORES)  # The branches too.
    query = queries[("C3", "B4", "A5")]
    assert (query["maxVisits"], query["priority"], query["rules"], query["komi"]) == (500, -100, "chinese", 0.5)
    assert query["overrideSettings"] == {"reportAnalysisWinratesAs": "BLACK", "wideRootNoise": 0.04, "maxTime": 30.0}
    assert (query["includePolicy"], query["includeOwnership"], query["analyzeTurns"]) == (True, True, [3])
    assert steps[-1] == ("first", 5, 5)
    mistake = game.nodes[3]
    assert game.points_lost(mistake) == 5.5
    assert game.analysis(mistake)["root"]["pv"] == ["A5", "E5", "A1"]  # As KaTrain: the move and the sequence.
    before = game.analysis(mistake.parent)["moves"]["A5"]
    assert (before["order"], before["scoreLead"]) == (ADDITIONAL_MOVE_ORDER, -5.0)  # The node before knows it.


def test_fast_visits():
    engine = FakeEngine()
    analyze_game(engine, root(), AnalysisSettings(fast=True, fast_visits=8), VALUES, lambda *_: None)
    assert {query["maxVisits"] for query in engine.queries} == {8}


def test_saved_analysis_data_is_used_as_it_is():
    """A node with analysis data (KT) is not analyzed again, as in KaTrain."""
    saved = {"moves": {}, "root": {"scoreLead": 1.0, "winrate": 0.5, "visits": 9}, "completed": True}
    text = GAME.replace(";B[cc]", ";B[cc]KT[" + "][".join(encode_kt(saved)) + "]")
    engine = FakeEngine()
    game = analyze_game(engine, GoGame.parse_sgf(text), AnalysisSettings(), VALUES, lambda *_: None)
    assert ("C3",) not in by_moves(engine) and len(engine.queries) == 4
    assert game.analysis(game.nodes[1])["root"]["visits"] == 9


def test_reanalysis_of_the_mistakes_only():
    """The node of the mistake and the node before it (its child lost points) are analyzed again."""
    engine = FakeEngine()
    settings = AnalysisSettings(reanalyze=True, mistakes_only=True, max_time=30.0)
    steps = []
    analyze_game(engine, root(), settings, VALUES, lambda *step: steps.append(step))
    again = engine.queries[5:]
    assert sorted(len(query["moves"]) for query in again) == [2, 3]
    assert {query["maxVisits"] for query in again} == {1000}  # The fewest visits (500) plus max_visits.
    assert {query["priority"] for query in again} == {-1_000_000}
    assert all("maxTime" not in query["overrideSettings"] for query in again)
    assert steps[-1] == ("again", 2, 2)


def test_reanalysis_of_a_range_uses_depth_minus_one_as_katrain():
    """KaTrain's range is checked against the depth - 1 of each node: moves 1 to 1 are the nodes of move 2."""
    engine = FakeEngine()
    settings = AnalysisSettings(reanalyze=True, reanalyze_visits=50, move_from=1, move_to=1)
    analyze_game(engine, root(), settings, VALUES, lambda *_: None)
    assert [(len(query["moves"]), query["maxVisits"]) for query in engine.queries[5:]] == [(2, 50)]


def test_a_failed_query_is_counted_and_the_others_are_kept():
    engine = FakeEngine(failing=("C3", "B4"))
    game = analyze_game(engine, root(), AnalysisSettings(), VALUES, lambda *_: None)
    assert game.failed == 1
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
    apply_answer(analysis, {"rootInfo": {"scoreLead": 0.0}, "moveInfos": []}, None, None)
    assert analysis["moves"]["A1"]["order"] == ADDITIONAL_MOVE_ORDER and analysis["completed"] is True


def test_no_query_when_stones_are_removed():
    node = GoGame.parse_sgf("(;SZ[5];B[cc];AE[cc];W[dd])").nodes_in_tree[-1]
    assert node_query(node, QuerySettings(10, 0.0, None, 0)) is None


def test_query_with_placed_stones():
    node = GoGame.parse_sgf("(;SZ[5]AB[aa][bb]PL[W];W[cc])").nodes_in_tree[-1]
    query = node_query(node, QuerySettings(10, 0.0, None, 0))
    assert query["initialStones"] == [["B", "A5"], ["B", "B4"]]
    assert (query["initialPlayer"], query["moves"], query["rules"]) == ("W", [["W", "C3"]], "japanese")
