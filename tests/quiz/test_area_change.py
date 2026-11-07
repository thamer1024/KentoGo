"""Tests for kentogo.quiz.area_change (the "地の違い" view: the areas after the game move and the best move)."""

from pysgf import GoGame

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.game_analysis import EngineValues
from kentogo.analysis.sgf_writer import WriteSettings, write_analysis
from kentogo.common.types import Move, Position
from kentogo.gui import texts
from kentogo.mistakes.problem import Problem
from kentogo.quiz.area_change import (
    AREAS_BEST,
    AREAS_CHANGE,
    AREAS_OFF,
    AREAS_PLAYED,
    AreaChange,
    AreaView,
    read_area_change,
)
from kentogo.quiz.transform import BoardTransform

GAME = "(;SZ[5]KM[0.5];B[cc];W[bb];B[aa])"  # Black's A5 (move 3) is the mistake.


class FakeEngine:
    """KataGo whose best move is always E5; the areas are black's after E5 and white's after A5."""

    def query(self, request, callback):
        moves = [point for _, point in request["moves"]]
        allowed = request.get("allowMoves", [{}])[0].get("moves")
        last = allowed[0] if allowed else (moves[-1] if moves else "")
        owner = 0.8 if last == "E5" else -0.8 if last == "A5" else 0.0
        score = {"E5": 1.0, "A5": -6.0}.get(last, 0.0)
        info = {
            "move": allowed[0] if allowed else "E5",
            "order": 0,
            "visits": 10,
            "scoreLead": score,
            "winrate": 0.5,
            "pv": ["E5"],
        }
        answer = {"id": "x", "rootInfo": {"scoreLead": score, "winrate": 0.5, "visits": 10}, "moveInfos": [info]}
        if request.get("includeOwnership", True):
            answer["ownership"] = [owner] * 25
        callback(answer)
        return "x"


def problem_of(path) -> Problem:
    position = Position(5, 0.5, "chinese", (), (Move.from_gtp("C3", "B"), Move.from_gtp("B4", "W")), "B")
    return Problem("id", str(path), 3, position, Move.from_gtp("A5", "B"), Move.from_gtp("E5", "B"), 7.0)


def analyzed_file(tmp_path, deep: bool = True):
    root = GoGame.parse_sgf(GAME)
    settings = AnalysisSettings()
    targets = DeepTargets({"B": 5.0} if deep else {}, 40)
    game = analyze_game(FakeEngine(), root, settings, EngineValues(10, 0.0), lambda *_: None, targets)
    write_analysis(game, WriteSettings(settings, "1.0"))
    path = tmp_path / "game.sgf"
    path.write_text(root.sgf(), encoding="utf-8")
    return path


def test_the_areas_after_both_moves_are_read_from_kentogos_data(tmp_path):
    change = read_area_change(problem_of(analyzed_file(tmp_path)))
    assert (change.played.gtp(), change.best.gtp()) == ("A5", "E5")
    assert round(change.played_areas[(0, 0)], 2) == -0.8 and round(change.best_areas[(0, 0)], 2) == 0.8  # 16 bits.
    assert (change.played_lead, change.best_lead) == (-6.0, 1.0)
    assert len(change.changed()) == 25 and change.gained("B") == 25 and change.lead_gain("B") == 7.0


def test_a_move_that_was_not_read_deeply_has_no_data(tmp_path):
    assert read_area_change(problem_of(analyzed_file(tmp_path, deep=False))) is None
    view = AreaView(problem_of(analyzed_file(tmp_path, deep=False)))
    assert view.next() == AREAS_OFF and view.missing


def test_the_view_goes_through_the_pictures(tmp_path):
    view = AreaView(problem_of(analyzed_file(tmp_path)))
    assert [view.next() for _ in range(4)] == [AREAS_PLAYED, AREAS_BEST, AREAS_CHANGE, AREAS_OFF]
    view.next()
    view.hide()
    assert view.mode == AREAS_OFF


def test_only_points_that_change_owner_enough_are_changes():
    change = AreaChange(
        Move.from_gtp("A1", "B"),
        Move.from_gtp("B1", "B"),
        {(0, 0): -0.3, (1, 0): 0.9, (2, 0): -0.1},
        {(0, 0): 0.4, (1, 0): 0.95, (2, 0): 0.2},
        None,
        None,
    )
    assert change.changed() == {(0, 0): 0.7}  # (1, 0) stays black's; (2, 0) moves only 0.3.
    assert change.lead_gain("B") is None


def test_the_change_follows_the_board_of_the_problem():
    """A swapped and turned board moves the points, and the owners and leads change sides."""
    change = AreaChange(Move.from_gtp("A1", "B"), Move.from_gtp("B1", "B"), {(0, 0): -0.6}, {(0, 0): 0.6}, -2.0, 3.0)
    shown = change.transformed(BoardTransform(symmetry=1, swap_colors=True), 5)
    point = BoardTransform(symmetry=1).point((0, 0), 5)
    assert shown.played.color == "W" and shown.best_areas == {point: -0.6} and shown.best_lead == -3.0
    assert shown.gained("W") == 1 and shown.lead_gain("W") == 5.0


def test_the_texts_of_the_view():
    change = AreaChange(Move.from_gtp("A1", "B"), Move.from_gtp("B1", "B"), {(0, 0): -0.6}, {(0, 0): 0.6}, -2.0, 3.0)
    assert "A1" in texts.area_text(change, AREAS_PLAYED) and "B1" in texts.area_text(change, AREAS_BEST)
    assert texts.area_text(change, AREAS_CHANGE).endswith("+1点、形勢 +5.0目")
