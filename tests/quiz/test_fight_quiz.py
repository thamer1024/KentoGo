"""Tests for kentogo.quiz.fight_quiz (the local fights of a sitting, against a fake KataGo)."""

from test_fight_judge import fight
from test_fight_run import FakeEngine

from kentogo.quiz.fight_judge import OUTCOME_USER_LEFT, OUTCOME_WON
from kentogo.quiz.fight_quiz import PHASE_ENDED, PHASE_ERROR, PHASE_TURN, PHASE_WAITING, FightQuiz
from kentogo.quiz.fight_run import FightPlay, FightRun


class Listener:
    def __init__(self):
        self.changes = 0

    def changed(self):
        self.changes += 1


class LaterEngine(FakeEngine):
    """Keeps the callbacks, to answer later (as KataGo does from its thread)."""

    def __init__(self, by_moves):
        super().__init__(by_moves)
        self.waiting = []

    def query(self, request, callback):
        self.waiting.append((request, callback))
        return "x"

    def answer(self):
        request, callback = self.waiting.pop(0)
        FakeEngine.query(self, request, callback)


def quiz_with(engine, count: int = 1) -> tuple[FightQuiz, list]:
    saved = []
    quiz = FightQuiz(
        [fight()] * count,
        lambda one: FightRun(engine, one, FightPlay(500, None)),
        saved.append,
        Listener(),
        lambda function: function,
    )
    quiz.start(0)
    return quiz, saved


def test_a_fight_is_played_and_saved():
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (0.5, 0.6, "B2"), 2: (0.0, 0.6, "D2"), 3: (0.0, 0.9, "J9")})
    quiz, saved = quiz_with(engine)
    assert quiz.phase == PHASE_TURN
    assert quiz.play((0, 1)) == "" and quiz.phase == PHASE_TURN  # A2, and white answered B2.
    assert quiz.play((2, 1)) == "" and quiz.phase == PHASE_ENDED  # C2: the stones live.
    assert saved == [quiz.run] and quiz.run.outcome.kind == OUTCOME_WON
    quiz.next_fight()
    assert quiz.run is None and quiz.index == 1


def test_moves_that_are_not_taken():
    """A stone on a stone is not allowed; a click while KataGo reads is not taken."""
    engine = LaterEngine({0: (1.0, 0.6, "B2"), 1: (0.5, 0.6, "B2")})
    quiz, _saved = quiz_with(engine)
    assert quiz.play((0, 1)) == ""  # Still starting: not taken.
    engine.answer()
    assert quiz.play((4, 4)) != ""  # White's stone of the position.
    assert quiz.play((0, 1)) == "" and quiz.phase == PHASE_WAITING
    assert quiz.play((2, 1)) == "" and len(quiz.run.played) == 1


def test_answers_about_a_fight_left_are_not_used():
    engine = LaterEngine({0: (1.0, 0.6, "B2")})
    quiz, _saved = quiz_with(engine, count=2)
    quiz.next_fight()
    engine.answer()  # The first fight's answer.
    assert quiz.index == 1 and quiz.phase != PHASE_TURN
    engine.answer()
    assert quiz.phase == PHASE_TURN


def test_leaving_the_fight_and_errors():
    engine = FakeEngine({0: (1.0, 0.6, "B2")})
    quiz, saved = quiz_with(engine)
    quiz.play((8, 8))  # J9, far from the fight.
    assert quiz.phase == PHASE_ENDED and saved[0].outcome.kind == OUTCOME_USER_LEFT

    quiz, saved = quiz_with(BrokenEngine())
    assert quiz.phase == PHASE_ERROR and "broken" in quiz.error and quiz.play((0, 1)) == ""
    assert saved == [] and quiz.run.played == ()


class BrokenEngine:
    def query(self, _request, callback):
        callback({"error": "broken"})
        return "x"
