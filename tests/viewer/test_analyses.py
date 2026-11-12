"""Tests for kentogo.viewer.analyses, with fake KataGo engines."""

from fake_analysis import FakeEngine
from pysgf import GoGame

from kentogo.common.types import Move
from kentogo.katago.evaluate import AnalysisModel, EvaluationSettings, Models
from kentogo.mistakes.problem import Variation
from kentogo.record.game_record import read_game_record
from kentogo.viewer.analyses import ESTIMATE_FAILED, NO_ENGINE, GameAnalyses

GAME = "(;SZ[9];B[cc];W[ai];B[bb];W[ia])"
SIZE = 9
SETTINGS = EvaluationSettings(max_visits=50, estimate_visits=10)


def record():
    """Read GAME."""
    return read_game_record(GoGame.parse_sgf(GAME))


class Told:
    """Keeps what the analyses tell the screen."""

    def __init__(self):
        """Start with nothing told."""
        self.estimated_at: list = []
        self.errors: list[tuple[str, str]] = []

    def estimated(self, key):
        """Keep the key of a new standing."""
        self.estimated_at.append(key)

    def failed(self, text_key, reason):
        """Keep an error."""
        self.errors.append((text_key, reason))


def make(main=None):
    """Make the analyses with a fake engine (None when the main model is not running), with a game open."""
    told = Told()
    analyses = GameAnalyses(Models(AnalysisModel(main, SETTINGS) if main is not None else None), told)
    analyses.open(record())
    return analyses, told


KATRAIN = Variation((Move.from_gtp("E5", "B"), Move.from_gtp("D4", "W")), "katrain")


def test_the_standing_is_calculated_with_the_main_model():
    """The end of the sequence and the game after the same number of moves are analyzed, and the standing kept."""
    main = FakeEngine()
    analyses, told = make(main)
    analyses.estimate("key", 3, KATRAIN)
    assert analyses.estimating and analyses.busy and len(main.queries) == 2
    end_moves, game_moves = main.queries[0][0]["moves"], main.queries[1][0]["moves"]
    assert end_moves == [["B", "C7"], ["W", "A1"], ["B", "E5"], ["W", "D4"]]
    assert game_moves == [["B", "C7"], ["W", "A1"], ["B", "B8"], ["W", "J9"]]
    main.answer_standing(0, lead=2.0, owner=1.0, size=SIZE)
    main.answer_standing(1, lead=-1.0, owner=-1.0, size=SIZE)
    assert not analyses.estimating and told.estimated_at == ["key"]
    assert analyses.standings["key"].gain == 3.0


def test_standing_failures_are_told():
    """Without the main model, or when KataGo fails, the reason is told."""
    without, told = make()
    without.estimate("key", 3, KATRAIN)
    assert told.errors == [(NO_ENGINE, "")] and not without.estimating
    main = FakeEngine()
    analyses, told = make(main)
    analyses.estimate("key", 3, KATRAIN)
    main.answer(0, error="KataGo stopped")
    assert told.errors[-1][0] == ESTIMATE_FAILED and not analyses.estimating


def test_an_answer_for_another_game_is_dropped():
    """When another game is opened meanwhile, the late standing is not kept."""
    main = FakeEngine()
    analyses, told = make(main)
    analyses.estimate("key", 3, KATRAIN)
    analyses.open(record())
    main.answer_standing(0, lead=2.0, owner=1.0, size=SIZE)
    main.answer_standing(1, lead=-1.0, owner=-1.0, size=SIZE)
    assert analyses.standings == {} and told.estimated_at == [] and not analyses.busy


def test_opening_another_game_forgets_the_results():
    """The standings belong to the game: they are forgotten when another one is opened."""
    main = FakeEngine()
    analyses, _ = make(main)
    analyses.estimate("key", 3, KATRAIN)
    main.answer_standing(0, lead=2.0, owner=1.0, size=SIZE)
    main.answer_standing(1, lead=-1.0, owner=-1.0, size=SIZE)
    assert analyses.standings
    analyses.open(record())
    assert analyses.standings == {}


def test_answers_pass_through_the_main_thread():
    """Every callback of KataGo is wrapped by in_main."""
    wrapped = []
    models = Models(AnalysisModel(FakeEngine(), SETTINGS))
    analyses = GameAnalyses(models, Told(), lambda function: wrapped.append(function) or function)
    analyses.open(record())
    analyses.estimate("key", 3, KATRAIN)
    assert len(wrapped) == 2
