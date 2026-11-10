"""Tests for kentogo.quiz.standings, with a fake KataGo engine and a game file."""

from fake_analysis import FakeEngine

from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import AnalysisModel, EvaluationSettings, Models
from kentogo.mistakes.problem import SOURCE_KATAGO_COMPARE, Problem, Variation
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import QuizSession
from kentogo.quiz.standings import FAILED, SequenceStandings
from kentogo.quiz.transform import BoardTransform

# A 9 x 9 game: black C7, white A1, black B8, white J9. The problem is black's move 3 (B8).
GAME = "(;SZ[9];B[cc];W[ai];B[bb];W[ia])"
SIZE = 9


def make_session(tmp_path, transform=BoardTransform()) -> QuizSession:
    """Answer the problem with its game move, so that KataGo's sequence after the answer can be shown."""
    path = tmp_path / "game.sgf"
    path.write_text(GAME)
    moves = (Move.from_gtp("C7", "B"), Move.from_gtp("A1", "W"))
    problem = Problem(
        problem_id="p1",
        sgf_path=str(path),
        move_number=3,
        position=Position(SIZE, 6.5, "japanese", (), moves, "B"),
        actual_move=Move.from_gtp("B8", "B"),
        best_move=Move.from_gtp("E5", "B"),
        points_lost=5.0,
        variations=(Variation((Move.from_gtp("E5", "B"), Move.from_gtp("D4", "W")), "katrain"),),
    )
    session = QuizSession(problem, ScoringPolicy(), transform)
    session.answer(transform.move(Move.from_gtp("E5", "B"), SIZE))
    session.step_forward()
    session.step_forward()  # The sequence is shown to its last move.
    return session


class Told:
    """Keeps what the standings tell the screen."""

    def __init__(self):
        """Start with nothing told."""
        self.changes = 0
        self.errors: list[tuple[str, str]] = []

    def changed(self):
        """Count a change."""
        self.changes += 1

    def failed(self, text_key, reason):
        """Keep an error."""
        self.errors.append((text_key, reason))


def models(main=None, compare=None) -> Models:
    """Make the models from fake engines (None for one that is not running)."""
    settings = EvaluationSettings(estimate_visits=10)
    return Models(
        AnalysisModel(main, settings) if main is not None else None,
        AnalysisModel(compare, settings) if compare is not None else None,
    )


def test_the_standing_is_calculated_by_itself_after_the_answer(tmp_path):
    """After the answer, the end of the sequence and the game are asked once; the standing is told at every step."""
    session, told, engine = make_session(tmp_path), Told(), FakeEngine()
    standings = SequenceStandings(session, background=lambda work: work())
    standings.prepare(models(engine), told.changed, told.failed)
    assert standings.busy and len(engine.queries) == 2 and standings.shown() is None
    engine.answer_standing(0, lead=3.0, owner=1.0, size=SIZE)  # The end of the sequence.
    engine.answer_standing(1, lead=-1.0, owner=-1.0, size=SIZE)  # The game after the same number of moves.
    assert not standings.busy and told.errors == [] and told.changes == 1
    shown = standings.shown()
    assert (shown.end.lead, shown.game.lead) == (3.0, -1.0) and standings.at_end() is not None
    session.step_back()
    assert standings.shown() is not None and standings.at_end() is None  # The territory only at the last move.
    standings.prepare(models(engine), told.changed, told.failed)
    assert len(engine.queries) == 2  # Not asked again.


def test_nothing_is_asked_before_the_answer(tmp_path):
    path = tmp_path / "game.sgf"
    path.write_text(GAME)
    session = make_session(tmp_path)
    fresh = QuizSession(session.problem, ScoringPolicy(), BoardTransform())
    engine = FakeEngine()
    SequenceStandings(fresh, background=lambda work: work()).prepare(models(engine), Told().changed, Told().failed)
    assert engine.queries == []


def test_the_game_is_read_from_the_file(tmp_path):
    """The game after the same number of moves (here move 4) is read from the SGF file."""
    session, engine = make_session(tmp_path), FakeEngine()
    SequenceStandings(session, background=lambda work: work()).prepare(models(engine), Told().changed, Told().failed)
    game_moves = engine.queries[1][0]["moves"]
    assert game_moves == [["B", "C7"], ["W", "A1"], ["B", "B8"], ["W", "J9"]]


def test_the_standing_follows_the_board(tmp_path):
    """With the colors swapped, the shown lead is from the other side."""
    session, engine = make_session(tmp_path, BoardTransform(0, swap_colors=True)), FakeEngine()
    standings = SequenceStandings(session, background=lambda work: work())
    standings.prepare(models(engine), Told().changed, Told().failed)
    engine.answer_standing(0, lead=3.0, owner=1.0, size=SIZE)
    engine.answer_standing(1, lead=-1.0, owner=-1.0, size=SIZE)
    assert standings.shown().end.lead == -3.0


def test_without_the_model_nothing_is_asked(tmp_path):
    """Without the model of the sequence, no standing is calculated, and nothing is told."""
    session, told = make_session(tmp_path), Told()
    standings = SequenceStandings(session, background=lambda work: work())
    standings.prepare(models(), told.changed, told.failed)
    assert told.errors == [] and not standings.busy and standings.shown() is None


def test_the_comparison_models_sequence_uses_its_own_model(tmp_path):
    """The standing at the end of the comparison model's sequence is calculated with the comparison model."""
    session = make_session(tmp_path)
    session.offer(SOURCE_KATAGO_COMPARE)
    session.apply_compare_evaluation(0.0, 5.0, (Move.from_gtp("E5", "B"), Move.from_gtp("D4", "W")), 0.0)
    main, compare = FakeEngine(), FakeEngine()
    SequenceStandings(session, background=lambda work: work()).prepare(
        models(main, compare), Told().changed, Told().failed
    )
    assert len(main.queries) == 2 and len(compare.queries) == 2  # The SGF's sequence, and the comparison model's.


def test_a_failure_is_told_once(tmp_path):
    """When KataGo or the file fails, the reason is told, and that sequence is not asked again."""
    session, told, engine = make_session(tmp_path), Told(), FakeEngine()
    standings = SequenceStandings(session, background=lambda work: work())
    standings.prepare(models(engine), told.changed, told.failed)
    engine.answer(0, error="KataGo stopped")
    assert not standings.busy and told.errors[0][0] == FAILED and "KataGo stopped" in told.errors[0][1]
    standings.prepare(models(engine), told.changed, told.failed)
    assert len(engine.queries) == 2 and len(told.errors) == 1


def test_a_missing_file_is_told(tmp_path):
    session, told, engine = make_session(tmp_path), Told(), FakeEngine()
    (tmp_path / "game.sgf").unlink()
    standings = SequenceStandings(session, background=lambda work: work())
    standings.prepare(models(engine), told.changed, told.failed)
    assert not standings.busy and told.errors[-1][0] == FAILED and engine.queries == []
