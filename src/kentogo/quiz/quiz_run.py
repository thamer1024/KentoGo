"""Ask a list of problems one after another, and judge the answers with KataGo (no screen).

The quiz screen shows what happens here and passes the user's actions on (see gui.quiz_screen).
This part decides:

- which problem is asked, and when the quiz has ended. The next problem can be asked at any time: what
  KataGo is still calculating for this one is stopped (an answer still judged is saved without losses);
- how an answer is judged: from the SGF file when its loss is there, otherwise with KataGo. While
  KataGo judges the answer, the sequences cannot be switched or played (busy), and the next problem
  waits until KataGo has finished everything for this one (calculating);
- KataGo's sequences after the answer and after the game move. In them, the user's moves are those of
  a human of the user's rank (else of the opponent's rank), and the opponent plays the strongest
  replies (the main KataGo's best moves, see quiz.human_line). Without any rank, KataGo's own sequences;
- saving each answer once, when its result is known (or without losses when it cannot be judged).
  A problem answered wrong is not asked again the same day: it is reviewed on a later day
  (see repetition.schedule).

KataGo answers in its own threads. Each callback is passed through in_main (the screen gives
one that runs it in its main thread), and then the listener is told what changed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from kentogo.common.board import IllegalMoveError
from kentogo.common.types import Move
from kentogo.katago.evaluate import (
    AnalysisEngine,
    AnalysisModel,
    Evaluation,
    EvaluationSettings,
    Models,
    evaluate_moves,
    predict_after,
)
from kentogo.katago.human_moves import human_profile
from kentogo.mistakes.problem import SOURCE_KATAGO_ACTUAL, SOURCE_KATAGO_ANSWER, Problem
from kentogo.quiz.human_line import Extension, LineEngines, PlayerRanks, build_line
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import ANSWERED, WAITING, QuizSession
from kentogo.quiz.transform import BoardTransform

# The sequences after the answer and after the game move are made as long as the longest sequence in the
# SGF file (KaTrain's), at least MIN_LINE moves, so that their ends can be compared; but no move is added
# after KataGo's own length once LINE_SECONDS have passed.
MIN_LINE = 15
LINE_SECONDS = 5.0

# Why an answer is not judged yet: the key of a screen text and its values.
REASON_EVALUATING = "evaluating"
REASON_NO_ENGINE = "no_engine"
REASON_FAILED = "evaluation_failed"

Reason = tuple[str, dict]
Saver = Callable[[QuizSession, int | None], None]


@dataclass(frozen=True)
class Judging:
    """KataGo for judging the answers and showing sequences.

    Attributes:
        engine: KataGo with the main model, or None if it is not available.
        settings: How the main model analyzes the positions.
        engine_problem: Why KataGo is not available ("" if it is available).
        player_ranks: Returns the ranks of the players of a problem's game, for the human-like moves of KataGo's
            sequences (see kentogo.opponent_rank; without a rank, KataGo's own sequences are shown).
    """

    engine: AnalysisEngine | None = None
    settings: EvaluationSettings = EvaluationSettings()
    engine_problem: str = ""
    player_ranks: Callable[[Problem], PlayerRanks] = lambda _problem: PlayerRanks()

    def models(self) -> Models:
        """Return the main model, for the territory and the standing."""
        return Models(AnalysisModel(self.engine, self.settings) if self.engine is not None else None)


class QuizListener(Protocol):
    """What the screen is told (always in its main thread, see in_main)."""

    def started(self, session: QuizSession | None) -> None:
        """A problem is asked now, or the quiz has ended (None)."""

    def changed(self, session: QuizSession) -> None:
        """The result or the sequences of a session changed (it may not be the one shown now)."""

    def failed(self, text_key: str, reason: str) -> None:
        """KataGo could not calculate something: the key of the message, and why."""


@dataclass
class QuizRun:
    """The problems of the quiz and the problem asked now.

    Attributes:
        problems: The problems to ask, in order.
        policy: The rule for deciding whether an answer is correct.
        choose_transform: Returns how to change each problem.
        judging: KataGo for judging the answers.
        listener: Told what changed.
        save: Saves an answer (the session, and KataGo's visits or None).
        in_main: Wraps a callback of KataGo so that it runs in the screen's main thread.
        index: The index of the problem asked now.
        session: The session of the problem asked now, or None after the last problem.
    """

    problems: list[Problem]
    policy: ScoringPolicy
    choose_transform: Callable[[], BoardTransform]
    judging: Judging
    listener: QuizListener
    save: Saver = lambda _session, _visits: None
    in_main: Callable[[Callable], Callable] = lambda function: function
    index: int = field(default=0, init=False)
    session: QuizSession | None = field(default=None, init=False)
    _waiting: set[QuizSession] = field(default_factory=set, init=False)  # Answers that KataGo is still judging.
    _reasons: dict[QuizSession, Reason] = field(default_factory=dict, init=False)  # Why answers are not judged.

    def start(self, index: int) -> None:
        """Ask the problem with the given index (after the last one, the quiz has ended)."""
        self.index = index
        if index >= len(self.problems):
            self.session = None
        else:
            self.session = QuizSession(self.problems[index], self.policy, self.choose_transform())
        self.listener.started(self.session)

    @property
    def busy(self) -> bool:
        """True while KataGo judges the answer of the problem asked now (it cannot be played or switched)."""
        return self.session is not None and self.session in self._waiting

    @property
    def calculating(self) -> bool:
        """True while KataGo judges the answer or calculates a sequence of the problem asked now."""
        session = self.session
        if session is None or session.phase != ANSWERED:
            return False
        return self.busy or any(choice.status == WAITING for choice in session.choices)

    def can_play(self) -> bool:
        """True if the shown sequence can be played back and forth now."""
        return self.session is not None and not self.busy

    def next_problem(self) -> bool:
        """Go to the next problem at once. Returns True if it went (False after the last one).

        While KataGo is still calculating for this problem, its answer still judged is saved without losses,
        and KataGo stops reading (see stop_katago); its late answers for this problem are not used.
        """
        if self.session is None:
            return False
        if self.calculating:
            self.save_unfinished()
            self.stop_katago()
        self.start(self.index + 1)
        return True

    def leave(self) -> None:
        """Leave the quiz (back to the top screen): save the answers KataGo is still judging, without losses,
        and make KataGo stop reading when it still calculates for the problem asked now (see stop_katago)."""
        calculating = self.calculating
        self.save_unfinished()
        if calculating:
            self.stop_katago()

    def stop_katago(self) -> None:
        """Ask KataGo to stop reading all queries, when it can (KataGo's "terminate_all")."""
        terminate_all = getattr(self.judging.engine, "terminate_all", None)
        if terminate_all is not None:
            terminate_all()

    def answer(self, point: tuple[int, int]) -> str:
        """Take a point of the shown board as the answer.

        Returns:
            "" when the answer was taken (or there is nothing to answer), or why the move is not allowed.
        """
        session = self.session
        if session is None or session.phase == ANSWERED:
            return ""
        try:
            result = session.answer(Move(session.shown_problem.position.next_color, point))
        except IllegalMoveError as error:
            return str(error)
        if result.correct is None:
            self._evaluate(session)
        else:
            self._judged_from_the_file(session)
        return ""

    def next_variation(self) -> bool:
        """Switch to the next sequence (after the answer, when not busy). Returns True if it switched."""
        session = self.session
        if session is None or session.phase != ANSWERED or self.busy:
            return False
        session.next_variation()
        return True

    def waiting_reason(self, session: QuizSession) -> Reason | None:
        """Return why the answer of a session is not judged yet (a text key and its values), or None."""
        return self._reasons.get(session)

    def save_unfinished(self) -> None:
        """Save the answers that KataGo is still judging, without losses (when the screen is left or the app closes)."""
        for session in list(self._waiting):
            self.save(session, None)
        self._waiting.clear()

    def _judged_from_the_file(self, session: QuizSession) -> None:
        """Save an answer judged from the SGF file, and ask KataGo for the sequences after it and after the game move."""
        self.save(session, None)
        answer = session.result.answer
        self._predict_after(session, answer, SOURCE_KATAGO_ANSWER)
        if answer != session.problem.actual_move:
            self._predict_after(session, session.problem.actual_move, SOURCE_KATAGO_ACTUAL)

    def _evaluate(self, session: QuizSession) -> None:
        """Ask KataGo for the losses of an answer whose loss is not in the SGF file."""
        engine = self.judging.engine
        if engine is None:
            self._reasons[session] = (REASON_NO_ENGINE, {"reason": self.judging.engine_problem})
            self.save(session, None)  # It cannot be judged, so it is saved without losses.
            return
        self._reasons[session] = (REASON_EVALUATING, {})
        self._waiting.add(session)
        session.expect(SOURCE_KATAGO_ANSWER)
        session.expect(SOURCE_KATAGO_ACTUAL)
        problem = session.problem
        evaluate_moves(
            engine,
            problem.position,
            session.result.answer,
            problem.actual_move,
            self.judging.settings,
            on_done=self.in_main(lambda evaluation: self._evaluated(session, evaluation)),
            on_error=self.in_main(lambda message: self._evaluation_failed(session, message)),
        )

    def _evaluated(self, session: QuizSession, evaluation: Evaluation) -> None:
        """Keep the losses that KataGo calculated, and save the answer (even if another problem is asked now)."""
        if session not in self._waiting:
            return  # Already saved without losses, because the screen was left.
        self._waiting.discard(session)
        session.apply_evaluation(evaluation.answer_loss, evaluation.actual_loss)  # The sequences come below.
        self._add_line(session, session.result.answer, evaluation.answer_sequence, SOURCE_KATAGO_ANSWER)
        self._add_line(session, session.problem.actual_move, evaluation.actual_sequence, SOURCE_KATAGO_ACTUAL)
        self._reasons.pop(session, None)
        self.save(session, self.judging.settings.max_visits)
        self.listener.changed(session)

    def _evaluation_failed(self, session: QuizSession, message: str) -> None:
        """Save the answer without losses, and tell why KataGo could not calculate them."""
        if session not in self._waiting:
            return
        self._waiting.discard(session)
        session.fail(SOURCE_KATAGO_ANSWER)
        session.fail(SOURCE_KATAGO_ACTUAL)
        self._reasons[session] = (REASON_FAILED, {"reason": message})
        self.save(session, None)
        self.listener.failed(REASON_FAILED, message)
        self.listener.changed(session)

    def _predict_after(self, session: QuizSession, move: Move, source: str) -> None:
        """Ask KataGo for the sequence after a move (SOURCE_KATAGO_ANSWER or SOURCE_KATAGO_ACTUAL)."""
        if self.judging.engine is None:
            return
        session.expect(source)
        predict_after(
            self.judging.engine,
            session.problem.position,
            move,
            self.judging.settings,
            on_done=self.in_main(lambda sequence: self._line_came(session, move, sequence, source)),
            on_error=self.in_main(lambda _message: self._predicted(session, move, (), source)),
        )

    def _line_came(self, session: QuizSession, move: Move, sequence: tuple[Move, ...], source: str) -> None:
        """Add KataGo's sequence after a move (see _add_line), and tell the screen."""
        self._add_line(session, move, sequence, source)
        self.listener.changed(session)

    def _add_line(self, session: QuizSession, move: Move, sequence: tuple[Move, ...], source: str) -> None:
        """Add the sequence after a move, with the user's human-like moves and the strongest replies when it can.

        KataGo's own sequence is added at once (without telling the screen); the sequence made with the
        user's human-like moves (see human_line) is added when it is made, and the screen is told then.
        """
        engines = self._own_line_engines(session.problem)
        if engines is None or not sequence or (source == SOURCE_KATAGO_ACTUAL and session.result.answer == move):
            self._keep_line(session, move, sequence, source)
            return
        session.expect(source)  # Still calculated (KataGo's own sequence is replaced).
        build_line(
            engines,
            session.problem.position,
            (move, *sequence),
            on_done=self.in_main(lambda line: self._predicted(session, move, line[1:], source)),
            on_error=self.in_main(lambda message: self._human_line_failed(session, move, sequence, source, message)),
            extension=Extension(_aimed_length(session.problem), LINE_SECONDS),
        )

    def _own_line_engines(self, problem: Problem) -> LineEngines | None:
        """Return what the sequences after the answer and after the game move are made with (None: KataGo's own).

        The user plays as a human of the user's rank (the opponent's when the user's is not known), and the
        opponent plays the strongest replies (see _strongest_replies).
        """
        judging = self.judging
        return _strongest_replies(judging.player_ranks(problem), judging.engine, judging.settings)

    def _human_line_failed(
        self, session: QuizSession, move: Move, sequence: tuple[Move, ...], source: str, message: str
    ) -> None:
        """Show KataGo's own sequence, and tell why the human-like replies could not be used (if still asked)."""
        self._predicted(session, move, sequence, source)
        if session is self.session:
            self.listener.failed("notice_human_line_failed", message)

    def _predicted(self, session: QuizSession, move: Move, sequence: tuple[Move, ...], source: str) -> None:
        """Add KataGo's sequence after a move, or mark it as failed, and tell the screen."""
        self._keep_line(session, move, sequence, source)
        self.listener.changed(session)

    def _keep_line(self, session: QuizSession, move: Move, sequence: tuple[Move, ...], source: str) -> None:
        """Add KataGo's sequence after a move, or mark it as failed."""
        if sequence:
            session.add_sequence(move, sequence, source)
        else:
            session.fail(source)


def _strongest_replies(
    ranks: PlayerRanks, engine: AnalysisEngine | None, settings: EvaluationSettings
) -> LineEngines | None:
    """Return what a sequence with the user's human-like moves and the strongest replies is made with.

    The opponent plays the main KataGo's best moves, reading estimate_visits for each (a short reading,
    so that a sequence is made in a few seconds). None without a rank or without the main KataGo.

    Args:
        ranks: The ranks of the players (the user's, else the opponent's, is the user's human-like rank).
        engine: The main KataGo (it has the human-like model).
        settings: The settings of the main KataGo.
    """
    my_profile = human_profile(ranks.mine or ranks.theirs)
    if not my_profile or engine is None:
        return None
    return LineEngines(engine, engine, settings.estimate_visits, settings.wide_root_noise, "", my_profile)


def _aimed_length(problem: Problem) -> int:
    """Return the length aimed at for the sequences made with the user's human-like moves (see MIN_LINE)."""
    return max([MIN_LINE, *(len(variation.moves) for variation in problem.variations)])
