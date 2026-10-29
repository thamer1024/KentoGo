"""Tests for kentogo.viewer.analyses, with fake KataGo engines."""

from fake_analysis import FakeEngine
from pysgf import GoGame

from kentogo.common.types import Move
from kentogo.katago.evaluate import AnalysisModel, EvaluationSettings, Models
from kentogo.mistakes.problem import SOURCE_KATAGO_COMPARE, Variation
from kentogo.record.game_record import read_game_record
from kentogo.viewer.analyses import COMPARE_FAILED, ESTIMATE_FAILED, NO_ENGINE, NO_SEQUENCE, GameAnalyses

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
        self.compared_at: list[int] = []
        self.estimated_at: list = []
        self.errors: list[tuple[str, str]] = []

    def compared(self, position):
        """Keep the position of a new sequence."""
        self.compared_at.append(position)

    def estimated(self, key):
        """Keep the key of a new standing."""
        self.estimated_at.append(key)

    def failed(self, text_key, reason):
        """Keep an error."""
        self.errors.append((text_key, reason))


def make(main=None, compare=None):
    """Make the analyses with fake engines (None for a model that is not running), with a game open."""
    told = Told()
    models = Models(
        AnalysisModel(main, SETTINGS) if main is not None else None,
        AnalysisModel(compare, SETTINGS) if compare is not None else None,
    )
    analyses = GameAnalyses(models, told)
    analyses.open(record())
    return analyses, told


def test_the_comparison_models_sequence_is_kept_for_its_move():
    """The comparison model analyzes the position before the move, and its sequence is kept for that move."""
    compare = FakeEngine()
    analyses, told = make(FakeEngine(), compare)
    assert analyses.can_compare(3)
    analyses.compare(3)
    assert analyses.analyzing == 3 and analyses.busy
    assert compare.queries[0][0]["moves"] == [["B", "C7"], ["W", "A1"]]
    compare.answer(0, score=1.0, pv=("E5", "D4"))
    assert not analyses.busy and told.compared_at == [3]
    assert analyses.lines[3] == Variation((Move.from_gtp("E5", "B"), Move.from_gtp("D4", "W")), SOURCE_KATAGO_COMPARE)
    assert not analyses.can_compare(3)  # Asked once for each move.


def test_the_comparison_model_is_asked_only_when_it_can_be():
    """Without the comparison model, or at the start of the game (no move), it is not asked."""
    without, _ = make(FakeEngine())
    assert not without.can_compare(3)
    analyses, _ = make(FakeEngine(), FakeEngine())
    assert not analyses.can_compare(0)


def test_comparison_failures_are_told():
    """No sequence, or an error, is told with its own message; the analyses are not busy any more."""
    compare = FakeEngine()
    analyses, told = make(FakeEngine(), compare)
    analyses.compare(3)
    compare.answer(0, score=1.0)
    analyses.compare(2)
    compare.answer(1, error="KataGo stopped")
    assert told.errors[0] == (NO_SEQUENCE, "") and told.errors[1][0] == COMPARE_FAILED
    assert "KataGo stopped" in told.errors[1][1] and not analyses.busy and analyses.lines == {}


def test_an_answer_for_another_game_is_dropped():
    """When another game is opened meanwhile, the late sequence is not kept."""
    compare = FakeEngine()
    analyses, told = make(FakeEngine(), compare)
    analyses.compare(3)
    analyses.open(record())
    compare.answer(0, score=1.0, pv=("E5",))
    assert analyses.lines == {} and told.compared_at == [] and not analyses.busy


def test_the_standing_is_calculated_with_the_model_of_the_sequence():
    """KaTrain's sequences use the main model, the comparison model's own sequences use it."""
    main, compare = FakeEngine(), FakeEngine()
    analyses, told = make(main, compare)
    katrain = Variation((Move.from_gtp("E5", "B"), Move.from_gtp("D4", "W")), "katrain")
    analyses.estimate("key", 3, katrain)
    assert analyses.estimating and len(main.queries) == 2 and compare.queries == []
    end_moves, game_moves = main.queries[0][0]["moves"], main.queries[1][0]["moves"]
    assert end_moves == [["B", "C7"], ["W", "A1"], ["B", "E5"], ["W", "D4"]]
    assert game_moves == [["B", "C7"], ["W", "A1"], ["B", "B8"], ["W", "J9"]]
    main.answer_standing(0, lead=2.0, owner=1.0, size=SIZE)
    main.answer_standing(1, lead=-1.0, owner=-1.0, size=SIZE)
    assert not analyses.estimating and told.estimated_at == ["key"]
    assert analyses.standings["key"].gain == 3.0
    own = Variation(katrain.moves, SOURCE_KATAGO_COMPARE)
    analyses.estimate("other", 3, own)
    assert len(compare.queries) == 2


def test_standing_failures_are_told():
    """Without the model, or when KataGo fails, the reason is told."""
    main = FakeEngine()
    analyses, told = make(main)
    own = Variation((Move.from_gtp("E5", "B"),), SOURCE_KATAGO_COMPARE)
    analyses.estimate("key", 3, own)
    assert told.errors == [(NO_ENGINE, "")] and not analyses.estimating
    analyses.estimate("key", 3, Variation((Move.from_gtp("E5", "B"),), "katrain"))
    main.answer(0, error="KataGo stopped")
    assert told.errors[-1][0] == ESTIMATE_FAILED and not analyses.estimating


def test_opening_another_game_forgets_the_results():
    """The sequences and standings belong to the game: they are forgotten when another one is opened."""
    compare = FakeEngine()
    analyses, _ = make(FakeEngine(), compare)
    analyses.compare(3)
    compare.answer(0, score=1.0, pv=("E5",))
    assert analyses.lines
    analyses.open(record())
    assert analyses.lines == {} and analyses.standings == {}


def test_answers_pass_through_the_main_thread():
    """Every callback of KataGo is wrapped by in_main."""
    wrapped = []
    models = Models(None, AnalysisModel(FakeEngine(), SETTINGS))
    analyses = GameAnalyses(models, Told(), lambda function: wrapped.append(function) or function)
    analyses.open(record())
    analyses.compare(3)
    assert len(wrapped) == 2
