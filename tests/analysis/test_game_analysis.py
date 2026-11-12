"""Tests for kentogo.analysis.analyze, game_analysis, node_analysis and query (the analysis of a game)."""

from pysgf import GoGame

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.game_analysis import EngineValues
from kentogo.analysis.node_analysis import ADDITIONAL_MOVE_ORDER, apply_answer, empty_analysis, update_move_analysis
from kentogo.analysis.played_moves import played_move_loss
from kentogo.analysis.query import QuerySettings, node_query
from kentogo.katago.presets import MIN_FAST_VISITS
from kentogo.record.katrain_kt import encode_kt
from kentogo.record.kentogo_analysis import KGA_PROPERTY, encode_kga

# Black's move 3 has two branches: A5 loses 5.5 points, D2 is fine.
GAME = "(;SZ[5]KM[0.5]RU[Chinese];B[cc];W[bb](;B[aa])(;B[db]))"
SCORES = {(): 0.0, ("C3",): 1.0, ("C3", "B4"): 0.5, ("C3", "B4", "A5"): -5.0, ("C3", "B4", "D4"): 0.6}
VALUES = EngineValues(max_visits=500, wide_root_noise=0.04)
FIRST = AnalysisSettings(fast_visits=VALUES.max_visits)  # The first analysis with the engine's visits.


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
            point, score = "E5", SCORES.get(moves, 0.0)
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
    game = analyze_game(engine, root(), FIRST, VALUES, lambda *step: steps.append(step))
    queries = by_moves(engine)
    assert set(queries) == set(SCORES)  # The branches too.
    query = queries[("C3", "B4", "A5")]
    assert (query["maxVisits"], query["priority"], query["rules"], query["komi"]) == (500, -100, "chinese", 0.5)
    assert query["overrideSettings"] == {"reportAnalysisWinratesAs": "BLACK", "wideRootNoise": 0.04}  # No time limit.
    assert (query["includePolicy"], query["includeOwnership"], query["analyzeTurns"]) == (True, False, [3])
    assert query["includeMovesOwnership"] is False  # The areas are never asked.
    assert ("first", 5, 5) in steps and steps[-1] == ("played", 4, 4)
    mistake = game.nodes[3]
    assert "pv" not in game.analysis(mistake)["root"]  # The answer is kept in its own node only.


def test_the_first_analysis_has_katrains_time_limit_and_the_deep_reading_none():
    """The first analysis and the played moves are read with max_time (as KaTrain opens a game); the deep reading is not."""
    engine = FakeEngine()
    values = EngineValues(max_visits=500, wide_root_noise=0.04, max_time=8.0)
    analyze_game(engine, root(), FIRST, values, lambda *_: None, DeepTargets({"B": 5.0}, 2000))
    limits = {(query["maxVisits"], query["overrideSettings"].get("maxTime")) for query in engine.queries}
    assert limits == {(500, 8.0), (2000, None)}
    assert {query["priority"] for query in analyses(engine) if query["maxVisits"] == 2000} == {-1_000_000}


def test_fast_visits():
    """Every position is read first with fast_visits, not the engine's visits (the played moves too), but never
    with fewer than MIN_FAST_VISITS: a low setting is raised to it."""
    engine = FakeEngine()
    analyze_game(engine, root(), AnalysisSettings(fast_visits=80), VALUES, lambda *_: None)
    assert {query["maxVisits"] for query in engine.queries} == {80}
    low = FakeEngine()
    analyze_game(low, root(), AnalysisSettings(fast_visits=8), VALUES, lambda *_: None)
    assert {query["maxVisits"] for query in low.queries} == {MIN_FAST_VISITS}


SAVED = {"moves": {}, "root": {"scoreLead": 1.0, "winrate": 0.5, "visits": 9}, "completed": True}


def with_saved(saved: dict, prop: str, mark: str = "") -> GoGame:
    """GAME with saved analysis data (KGA or KT) on the node of C3, and the root's KGM when mark is given."""
    values = encode_kga(saved) if prop == KGA_PROPERTY else encode_kt(saved)
    text = GAME.replace(";B[cc]", f";B[cc]{prop}[" + "][".join(values) + "]")
    return GoGame.parse_sgf(text.replace("(;", f"(;KGM[{mark}]", 1) if mark else text)


def test_saved_analysis_data_is_used_as_it_is():
    """A node with KentoGo's analysis data (KGA, or an older KentoGo's KT) is not analyzed again, as in KaTrain."""
    for root in (with_saved(SAVED, KGA_PROPERTY), with_saved(SAVED, "KT", "KentoGo")):
        engine = FakeEngine()
        game = analyze_game(engine, root, FIRST, VALUES, lambda *_: None)
        assert ("C3",) not in by_moves(engine) and len(analyses(engine)) == 4
        assert game.analysis(game.nodes[1])["root"]["visits"] == 9


def test_katrains_own_analysis_data_is_read_again():
    """KaTrain's KT (a game without KGM[KentoGo]) is not used: KentoGo reads the position itself."""
    engine = FakeEngine()
    analyze_game(engine, with_saved(SAVED, "KT"), FIRST, VALUES, lambda *_: None)
    assert ("C3",) in by_moves(engine)


def test_a_failed_query_is_asked_again_and_the_others_are_kept():
    """A failed node is asked again (retries times), and the nodes that still fail are kept."""
    once = FakeEngine(failing=("C3", "B4"), times=1)
    assert analyze_game(once, root(), FIRST, VALUES, lambda *_: None).failed == 0
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


def test_each_played_move_is_read_in_the_position_before_it():
    """The played move is read with only it allowed, as deeply as the position."""
    engine = FakeEngine()
    game = analyze_game(engine, root(), FIRST, VALUES, lambda *_: None)
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
    game = analyze_game(engine, root(), FIRST, VALUES, lambda *_: None)
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
        analyze_game(engine, GoGame.parse_sgf(game_text), FIRST, VALUES, lambda *_: None)
        assert len(played(engine)) == expected


def test_moves_that_can_become_problems_are_read_deeply():
    """Black's A5 lost 6.5 points: the positions before and after it, and A5 itself, are read with the deep visits."""
    engine = FakeEngine()
    targets = DeepTargets({"B": 5.0, "W": 1.0}, 2000)
    steps = []
    game = analyze_game(engine, root(), FIRST, VALUES, lambda *step: steps.append(step), targets)
    deep = [query for query in engine.queries if query["maxVisits"] == 2000]
    positions = [query for query in deep if "allowMoves" not in query and by_moves_of(query) in SCORES]
    assert sorted(len(query["moves"]) for query in positions) == [2, 3]
    assert [query["allowMoves"][0]["moves"] for query in deep if "allowMoves" in query] == [["A5"]]
    assert [node.depth for node in game.deep_nodes] == [3]  # White gained.
    assert ("deep", 2, 2) in steps
    assert played_move_loss(game, game.nodes[3]) == 6.5


def allowed(engine: FakeEngine, visits: int) -> list[list[str]]:
    """The played moves read with these visits."""
    return [query["allowMoves"][0]["moves"] for query in played(engine) if query["maxVisits"] == visits]


def test_only_the_played_moves_that_may_be_read_deeply_are_read():
    """With deep reading, a played move is read only when it lost at least 2/3 of the smallest loss of its color."""
    engine = FakeEngine()
    analyze_game(engine, root(), FIRST, VALUES, lambda *_: None, DeepTargets({"B": 5.0, "W": 1.0}, 2000))
    assert allowed(engine, 500) == [["A5"]]  # Not C3, B4 and D4, which gained or lost little.


def test_a_played_move_below_the_share_keeps_the_loss_known_so_far():
    """A5 lost 5.5 points by KaTrain's way: it is read from a smallest loss of 8 (5.33), not from 9 (6)."""
    for smallest, read, loss in ((8.0, [["A5"]], 6.5), (9.0, [], 5.5)):
        engine = FakeEngine()
        targets = DeepTargets({"B": smallest}, 2000)
        game = analyze_game(engine, root(), FIRST, VALUES, lambda *_: None, targets)
        assert allowed(engine, 500) == read and played_move_loss(game, game.nodes[3]) == loss


def test_only_the_biggest_losses_are_read_deeply():
    """With max_moves, the moves of both colors are taken together, the biggest losses first, in the game's order."""
    found = {}
    for most in (0, 2, 1):
        engine = FakeEngine()
        targets = DeepTargets({"B": -1.0, "W": -1.0}, 2000, max_moves=most)
        game = analyze_game(engine, root(), FIRST, VALUES, lambda *_: None, targets)
        found[most] = (allowed(engine, 2000), len(game.deep_nodes))
    assert found[0] == ([["C3"], ["A5"], ["D4"]], 3)  # No limit.
    assert found[2] == ([["A5"], ["D4"]], 2)  # A5 lost 6.5 points, D4 0.9, C3 0.
    assert found[1] == ([["A5"]], 1)


def deep_moves_of(mine: set[str], most: int, reply_loss: float) -> list[list[str]]:
    """The played moves read with the deep visits, when the user plays mine (every move loses at least -2)."""
    engine = FakeEngine()
    targets = DeepTargets(
        {"B": -2.0, "W": -2.0}, 2000, max_moves=most, my_colors=frozenset(mine), reply_loss=reply_loss
    )
    analyze_game(engine, root(), FIRST, VALUES, lambda *_: None, targets)
    return allowed(engine, 2000)


def test_the_opponents_moves_take_at_most_half_of_the_moves_read_deeply():
    """White is the user: black's C3 (lost 0) comes before white's B4 (gained 1.5), but takes at most half."""
    assert deep_moves_of({"B", "W"}, 2, -2.0) == [["A5"], ["D4"]]  # Both are the user's: the biggest losses.
    assert deep_moves_of({"W"}, 2, -2.0) == [["C3"], ["B4"]]  # C3, and white's reply B4 read again.
    assert deep_moves_of({"W"}, 1, -2.0) == [["B4"]]  # No place for black: half of 1 is 0.


def test_an_opponents_move_is_read_deeply_only_when_it_was_not_punished():
    """Black's C3 is read deeply only when white's reply B4 lost at least reply_loss (B4 gained 1.5 points)."""
    assert deep_moves_of({"W"}, 2, -2.0) == [["C3"], ["B4"]]
    assert deep_moves_of({"W"}, 2, -1.0) == [["B4"]]  # White punished C3 well enough: only B4 itself.


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
    assert analyze_game(engine, root(), FIRST, VALUES, lambda *_: None).deep_nodes == []
    game = analyze_game(FakeEngine(), root(), AnalysisSettings(), VALUES, lambda *_: None, DeepTargets({"W": 0}, 900))
    assert [node.move.player for node in game.deep_nodes] == []  # White's B4 gained 1.5 points (a loss below 0).


def test_a_handicap_game_is_decided_without_the_winrate():
    """In a handicap game, the rule gets no winrate, and the lead gained since the start (here the same lead)."""
    by_winrate = {"decided": lambda winrate, lead: winrate is not None}
    even = DeepTargets({"B": 5.0}, 2000, **by_winrate)
    handicap = DeepTargets({"B": 5.0}, 2000, handicap=True, **by_winrate)
    assert analyze_game(FakeEngine(), root(), AnalysisSettings(), VALUES, lambda *_: None, even).deep_nodes == []
    game = analyze_game(FakeEngine(), root(), AnalysisSettings(), VALUES, lambda *_: None, handicap)
    assert [node.depth for node in game.deep_nodes] == [3]


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


class LeftAgainEngine(FakeEngine):
    """Black (the opponent) plays C3 and A5, white (the user) B4 and D4; D4 does not punish A5 (it loses 4 points).

    The best move before A5 is E5; the best move before C3 (black's move before) is first_best.
    """

    SCORES = {(): 0.0, ("C3",): 0.0, ("C3", "B4"): 0.0, ("C3", "B4", "A5"): -5.0, ("C3", "B4", "A5", "D4"): -1.0}

    def __init__(self, first_best: str):
        super().__init__()
        self.first_best = first_best

    def query(self, request, callback):
        self.queries.append(request)
        moves = tuple(point for _, point in request["moves"])
        if "allowMoves" in request:
            point = request["allowMoves"][0]["moves"][0]
            score = self.SCORES.get((*moves, point), 0.0)
        else:
            point, score = (self.first_best if moves == () else "E5"), self.SCORES.get(moves, 0.0)
        candidate = {"move": point, "order": 0, "visits": request["maxVisits"], "scoreLead": score, "pv": [point]}
        root_info = {"scoreLead": score, "winrate": 0.5, "visits": request["maxVisits"]}
        callback({"id": "x", "rootInfo": root_info, "moveInfos": [candidate], "ownership": [0.0] * 25})
        return "x"


def test_an_opponents_move_that_only_left_the_same_point_again_is_not_read_deeply():
    """Black's A5 is read deeply only when E5, its best move, was not already black's best move before C3."""
    game_text = "(;SZ[5]KM[0.5]RU[Chinese];B[cc];W[bb];B[aa];W[db])"
    found = {}
    for first_best in ("E1", "E5"):
        engine = LeftAgainEngine(first_best)
        targets = DeepTargets({"B": 3.0, "W": 100.0}, 2000, my_colors=frozenset({"W"}), reply_loss=2.0)
        analyze_game(engine, GoGame.parse_sgf(game_text), FIRST, VALUES, lambda *_: None, targets)
        found[first_best] = allowed(engine, 2000)
    assert ["A5"] in found["E1"]
    assert found["E5"] == []
