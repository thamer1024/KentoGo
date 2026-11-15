"""Tests for kentogo.analysis.life_death, and the local fights step of the analysis (analysis.analyze)."""

from pysgf import GoGame
from test_game_analysis import FIRST, GAME, VALUES, FakeEngine

from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.life_death import (
    KIND_BOUNDARY,
    KIND_LIFE_DEATH,
    LocalChange,
    change_of,
    fight_start,
    local_change,
    stones_after,
    strongest_changes,
)
from kentogo.analysis.sgf_writer import WriteSettings, write_analysis
from kentogo.record.kentogo_analysis import read_kentogo_analysis

BLACK = [1.0] * 25  # Every point is black's.
WHITE = [-1.0] * 25  # Every point is white's.
# Black's A5 (after C3 and B4) gives everything to white: the black stones C3 and A5 die and the white B4 lives.
AREAS = {("C3", "B4"): BLACK, ("C3", "B4", "A5"): WHITE}


class AreasEngine(FakeEngine):
    """The fake engine of the analysis tests, with the areas of AREAS (0 elsewhere)."""

    def query(self, request, callback):
        moves = tuple(point for _, point in request["moves"])

        def with_areas(answer):
            if "rootInfo" in answer and request.get("includeOwnership"):
                answer = {**answer, "ownership": AREAS.get(moves, [0.0] * 25)}
            callback(answer)

        return super().query(request, with_areas)


def a5():
    """Black's A5 in GAME (after C3 and B4)."""
    return GoGame.parse_sgf(GAME).root.children[0].children[0].children[0]


def test_life_and_death():
    """Stones that went over to the opponent lose a life and death fight; fewer than MIN_STONES are a sacrifice."""
    stones = {(0, 0): "B", (1, 0): "B", (2, 2): "W", (4, 4): "B"}
    before = {(0, 0): 0.9, (1, 0): 0.6, (2, 2): 0.7, (4, 4): 0.9}
    after = {(0, 0): -0.8, (1, 0): -0.5, (2, 2): -0.9, (4, 4): 0.2}
    assert local_change(stones, before, after, "B", 0.0) == LocalChange(KIND_LIFE_DEATH, ("A1", "B1"), ("C3",), ())
    assert local_change({(0, 0): "B", (1, 0): "B"}, before, after, "B", 0.0) is None
    flipped = {point: -value for point, value in before.items()}, {point: -value for point, value in after.items()}
    white = {(0, 0): "W", (1, 0): "W", (2, 2): "B"}
    assert local_change(white, *flipped, "W", 0.0) == LocalChange(KIND_LIFE_DEATH, ("A1", "B1"), ("C3",), ())


def test_broken_boundary():
    """Empty points of the user that are no longer the user's are a broken boundary, when the move lost enough."""
    before = {(x, 0): 0.8 for x in range(6)} | {(9, 9): 0.3}
    after = {(x, 0): 0.0 for x in range(5)} | {(5, 0): 0.6, (9, 9): -0.9}
    found = local_change({}, before, after, "B", 2.0)
    assert found == LocalChange(KIND_BOUNDARY, (), (), ("A1", "B1", "C1", "D1", "E1")) and found.size == 5
    assert local_change({}, before, after, "B", 1.9) is None  # A territory given for something bigger.
    assert local_change({}, before | {(4, 0): 0.4}, after, "B", 5.0) is None  # Only 4 points were the user's.


def test_change_of_a_node():
    """The stones after the move are compared; a missing area or analysis gives None."""
    node = a5()
    assert stones_after(node) == {(2, 2): "B", (1, 3): "W", (0, 4): "B"}
    found = change_of(node, {"ownership": BLACK}, {"ownership": WHITE}, 6.0)
    assert found.kind == KIND_LIFE_DEATH and (found.mine, found.theirs) == (("A5", "C3"), ("B4",))
    assert len(found.points) == 22 and found.size == 25  # The empty points that were black's too.
    assert found.as_data(2)["kind"] == KIND_LIFE_DEATH and found.as_data(2)["moves"] == 2
    assert change_of(node, {"ownership": BLACK}, {}, 6.0) is None
    assert change_of(node, None, {"ownership": WHITE}, 6.0) is None


def test_fight_start():
    """The problem starts at the opponent's first move into the user's area near the changed points."""
    node = a5()
    change = LocalChange(KIND_LIFE_DEATH, ("A5",), ("B4",), ())
    white = node.parent  # White's B4.
    assert fight_start(node, change, lambda _position: {(1, 3): 0.9}) is white  # B4 was black's: white came in.
    assert fight_start(node, change, lambda _position: {(1, 3): -0.9}) is white  # Else just before black's move.
    far = LocalChange(KIND_LIFE_DEATH, ("E1",), (), ())
    assert fight_start(node, far, lambda _position: {(1, 3): 0.9}) is white  # B4 is not near E1: not followed.


def test_strongest_changes():
    """The moves that changed the most points are taken, the earlier one first, in the order of the game."""
    small = LocalChange(KIND_LIFE_DEATH, ("A1",) * 3, (), ())
    big = LocalChange(KIND_LIFE_DEATH, ("A1",) * 5, (), ())
    other = LocalChange(KIND_BOUNDARY, (), (), ("B1",) * 3)
    assert strongest_changes([("a", small), ("b", big), ("c", other)], 2) == ["a", "b"]


def test_the_analysis_finds_and_keeps_a_local_fight():
    """With deep reading, the areas are asked, black's A5 is read deeply with its areas, and the fight is kept where
    it started (after white's B4, which came into black's area)."""
    engine = AreasEngine()
    root = GoGame.parse_sgf(GAME).root
    game = analyze_game(engine, root, FIRST, VALUES, lambda *_: None, DeepTargets({"B": 50.0}, 2000, my_colors={"B"}))
    b4 = root.children[0].children[0]
    assert list(game.local_fights) == [id(b4)]
    fight = game.local_fights[id(b4)]
    assert (fight["kind"], fight["mine"], fight["theirs"], fight["moves"]) == (KIND_LIFE_DEATH, ["A5", "C3"], ["B4"], 1)
    deep = [query for query in engine.queries if query["maxVisits"] == 2000]
    assert sorted(len(query["moves"]) for query in deep) == [2, 3] and all(q["includeOwnership"] for q in deep)
    write_analysis(game, WriteSettings("test"))
    assert read_kentogo_analysis(b4)["local_fight"] == fight
    assert read_kentogo_analysis(b4).get("ownership") is None  # The areas themselves are not kept.


def test_no_areas_without_deep_reading():
    """Without deep reading (no targets), the areas are not asked and nothing is found."""
    engine = AreasEngine()
    game = analyze_game(engine, GoGame.parse_sgf(GAME).root, FIRST, VALUES, lambda *_: None)
    assert game.local_fights == {} and not any(query["includeOwnership"] for query in engine.queries)
