"""Tests for kentogo.quiz.fight_quiz (the local fights of a sitting, against a fake KataGo)."""

from test_fight_judge import fight
from test_fight_run import FakeEngine

from kentogo.quiz.fight_follow import END_MIXED, FollowEnd
from kentogo.quiz.fight_judge import OUTCOME_USER_LEFT, OUTCOME_WON
from kentogo.quiz.fight_lines import AI_CALCULATING, AI_READY, LINE_AI, LINE_STRONG
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
    assert quiz.lines.shown() == quiz.run.played and quiz.lines.ai_state == AI_CALCULATING  # Not made until asked.
    quiz.next_fight()
    assert quiz.run is None and quiz.index == 1


def test_the_sequence_of_the_ais_is_made_when_it_is_asked_for():
    """Tab: KataGo makes it from the fight's position until the stones are settled, and the user steps through it."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (0.5, 0.6, "B2"), 2: (0.0, 0.6, "D2"), 3: (0.0, 0.9, "J9")})
    quiz, _saved = quiz_with(engine)
    quiz.step_forward()  # Nothing is shown while the fight goes on.
    quiz.play((0, 1))
    quiz.play((2, 1))
    queries = len(engine.queries)
    quiz.follow()
    lines = quiz.lines
    assert (lines.name, lines.ai_state, lines.length, lines.step) == (LINE_AI, AI_READY, 3, 1)
    quiz.step_forward()
    quiz.step_forward()
    quiz.step_forward()  # Not after the last move.
    assert lines.step == 3
    quiz.step_back()
    assert lines.step == 2
    asked = len(engine.queries)
    quiz.follow()  # Asked again: the sequence is not made again.
    assert len(engine.queries) == asked and asked > queries and lines.step == 2
    assert quiz.play((4, 4)) == "" and len(quiz.run.played) == 3  # No stone can be put on the board.


def ended_quiz() -> tuple[FightQuiz, FakeEngine]:
    """A quiz whose fight has ended: black played A2 and C2, white answered B2."""
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (0.5, 0.6, "B2"), 2: (0.0, 0.6, "D2"), 3: (0.0, 0.9, "J9")})
    quiz, _saved = quiz_with(engine)
    quiz.play((0, 1))
    quiz.play((2, 1))
    return quiz, engine


def test_the_strongest_ai_plays_again_when_the_ais_did_not_conclude():
    """The human-like sequence settled the stones: no second sequence; a split end brings the strongest AI."""
    quiz, engine = ended_quiz()
    quiz.follow()
    assert not quiz.lines.strong_asked
    quiz._follow_done((), FollowEnd(END_MIXED, None, 3, 2))
    lines = quiz.lines
    assert (lines.strong_asked, lines.name, lines.count) == (True, LINE_STRONG, 4)  # Shown from the first move.
    assert (lines.strong_state, lines.length, lines.step) == (AI_READY, 3, 1)  # The fake KataGo answers at once.
    asked = len(engine.queries)
    quiz._follow_done((), FollowEnd(END_MIXED, None, 3, 2))  # Asked again: it is not made again.
    assert len(engine.queries) == asked


def test_what_katago_is_making_is_told_while_it_is_coming():
    """Nothing before the sequences are asked; LINE_AI while the sequence of the AIs is coming, then the strongest's."""
    engine = LaterEngine({0: (1.0, 0.6, "B2"), 1: (0.5, 0.6, "B2"), 2: (0.0, 0.6, "D2"), 3: (0.0, 0.9, "J9")})
    quiz, _saved = quiz_with(engine)
    assert quiz.calculating_line is None  # The fight is not asked yet (no sequences).
    engine.answer()
    quiz.play((0, 1))
    engine.answer()
    quiz.play((2, 1))
    engine.answer()
    assert quiz.calculating_line is None  # The fight has ended; the sequence of the AIs is not asked yet.
    quiz.follow()
    assert quiz.calculating_line == LINE_AI
    while engine.waiting:
        engine.answer()
    assert quiz.calculating_line is None  # Made (the stones are settled).
    quiz.lines.start_strong_line()
    assert quiz.calculating_line == LINE_STRONG
    quiz.lines.set_strong_line((), FollowEnd(END_MIXED, None, 1, 1))
    assert quiz.calculating_line is None


def test_follow_goes_to_and_fro_between_the_two_sequences_of_the_ais():
    """After the strongest AI has played again, Tab shows the human-like sequence, then the strongest's again."""
    quiz, _engine = ended_quiz()
    quiz.follow()
    quiz._follow_done((), FollowEnd(END_MIXED, None, 3, 2))
    assert quiz.lines.name == LINE_STRONG
    quiz.follow()
    assert quiz.lines.name == LINE_AI
    quiz.follow()
    assert (quiz.lines.name, quiz.lines.step) == (LINE_STRONG, 1)  # From its first move.
    quiz.follow()
    assert quiz.lines.name == LINE_AI


def test_the_strongest_ai_plays_also_when_the_ais_failed():
    quiz, _engine = ended_quiz()
    quiz._follow_failed("broken")
    assert quiz.lines.strong_asked and quiz.lines.name == LINE_STRONG


def test_a_fight_with_no_point_to_judge_is_not_asked():
    """The stones are white's whatever black plays: nothing to judge, so the fight is passed over unsaved."""
    engine = FakeEngine({0: (1.0, -0.6, "B2")})
    quiz, saved = quiz_with(engine, count=2)
    assert quiz.run is None and quiz.index == 2 and saved == []


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
    engine = FakeEngine({0: (1.0, 0.6, "B2"), 1: (1.0, 0.6, "C2"), 2: (1.0, 0.6, "D2")})  # With the AIs' line.
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
