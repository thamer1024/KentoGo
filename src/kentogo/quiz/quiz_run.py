"""Ask a list of problems one after another, and judge the answers with KataGo (no screen).

The quiz screen shows what happens here and passes the user's actions on (see gui.quiz_screen).
This part decides:

- which problem is asked, and when the quiz has ended;
- how an answer is judged: from the SGF file when its loss is there, otherwise with KataGo
  (the main model, or the comparison model when it judges). While KataGo judges the answer, the
  sequences cannot be switched or played (busy), and the next problem waits until KataGo has
  finished everything for this one (calculating);
- KataGo's sequences after the answer and after the game move, and the comparison model's
  sequence, which is asked only when the user first chooses it (so that it does not slow down
  the result);
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
from kentogo.mistakes.problem import SOURCE_KATAGO_ACTUAL, SOURCE_KATAGO_ANSWER, SOURCE_KATAGO_COMPARE, Problem
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.session import ANSWERED, OFFERED, WAITING, QuizSession
from kentogo.quiz.transform import BoardTransform

# Why an answer is not judged yet: the key of a screen text and its values.
REASON_EVALUATING = "evaluating"
REASON_NO_ENGINE = "no_engine"
REASON_FAILED = "evaluation_failed"

Reason = tuple[str, dict]
Saver = Callable[[QuizSession, int | None, bool], None]


@dataclass(frozen=True)
class Judging:
    """KataGo for judging the answers and showing sequences.

    Attributes:
        engine: KataGo with the main model, or None if it is not available.
        settings: How the main model analyzes the positions.
        engine_problem: Why KataGo is not available ("" if it is available).
        compare_engine: KataGo with the comparison model, or None.
        compare_settings: How the comparison model analyzes the positions (its own visits).
        judge_with_compare: True to calculate the losses with the comparison model.
    """

    engine: AnalysisEngine | None = None
    settings: EvaluationSettings = EvaluationSettings()
    engine_problem: str = ""
    compare_engine: AnalysisEngine | None = None
    compare_settings: EvaluationSettings = EvaluationSettings()
    judge_with_compare: bool = False

    @property
    def judges_with_compare(self) -> bool:
        """True if the comparison model judges the answers (it must be there)."""
        return self.judge_with_compare and self.compare_engine is not None

    @property
    def judge_engine(self) -> AnalysisEngine | None:
        """The KataGo that judges the answers."""
        return self.compare_engine if self.judges_with_compare else self.engine

    @property
    def judge_settings(self) -> EvaluationSettings:
        """How the model that judges the answers analyzes the positions."""
        return self.compare_settings if self.judges_with_compare else self.settings

    def models(self) -> Models:
        """Return the main model and the comparison model, for the territory and the standing."""
        main = AnalysisModel(self.engine, self.settings) if self.engine is not None else None
        if self.compare_engine is None:
            return Models(main)
        return Models(main, AnalysisModel(self.compare_engine, self.compare_settings))


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
        save: Saves an answer (the session, KataGo's visits or None, True if the comparison model judged it).
        in_main: Wraps a callback of KataGo so that it runs in the screen's main thread.
        index: The index of the problem asked now.
        session: The session of the problem asked now, or None after the last problem.
    """

    problems: list[Problem]
    policy: ScoringPolicy
    choose_transform: Callable[[], BoardTransform]
    judging: Judging
    listener: QuizListener
    save: Saver = lambda _session, _visits, _compare: None
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
            problem = self.problems[index]
            use_sgf_losses = not self.judging.judges_with_compare
            self.session = QuizSession(problem, self.policy, self.choose_transform(), use_sgf_losses=use_sgf_losses)
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
        """Go to the next problem, unless KataGo is still calculating for this one. Returns True if it went."""
        if self.session is None or self.calculating:
            return False
        self.start(self.index + 1)
        return True

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
        if self.judging.compare_engine is not None:
            session.offer(SOURCE_KATAGO_COMPARE)  # Calculated only when the user chooses it.
        return ""

    def next_variation(self) -> bool:
        """Switch to the next sequence (after the answer, when not busy). Returns True if it switched.

        When the comparison model's sequence is chosen for the first time, it is calculated.
        """
        session = self.session
        if session is None or session.phase != ANSWERED or self.busy:
            return False
        session.next_variation()
        choice = session.choice
        if choice is not None and choice.source == SOURCE_KATAGO_COMPARE and choice.status == OFFERED:
            self._ask_compare(session)
        return True

    def waiting_reason(self, session: QuizSession) -> Reason | None:
        """Return why the answer of a session is not judged yet (a text key and its values), or None."""
        return self._reasons.get(session)

    def save_unfinished(self) -> None:
        """Save the answers that KataGo is still judging, without losses (when the screen is left or the app closes)."""
        for session in list(self._waiting):
            self.save(session, None, False)
        self._waiting.clear()

    def _judged_from_the_file(self, session: QuizSession) -> None:
        """Save an answer judged from the SGF file, and ask KataGo for the sequences after it and after the game move."""
        self._finish(session, None, False)
        answer = session.result.answer
        self._predict_after(session, answer, SOURCE_KATAGO_ANSWER)
        if answer != session.problem.actual_move:
            self._predict_after(session, session.problem.actual_move, SOURCE_KATAGO_ACTUAL)

    def _evaluate(self, session: QuizSession) -> None:
        """Ask KataGo for the losses of an answer whose loss is not in the SGF file."""
        engine = self.judging.judge_engine
        if engine is None:
            self._reasons[session] = (REASON_NO_ENGINE, {"reason": self.judging.engine_problem})
            self.save(session, None, False)  # It cannot be judged, so it is saved without losses.
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
            self.judging.judge_settings,
            on_done=self.in_main(lambda evaluation: self._evaluated(session, evaluation)),
            on_error=self.in_main(lambda message: self._evaluation_failed(session, message)),
        )

    def _evaluated(self, session: QuizSession, evaluation: Evaluation) -> None:
        """Keep the losses that KataGo calculated, and save the answer (even if another problem is asked now)."""
        if session not in self._waiting:
            return  # Already saved without losses, because the screen was left.
        self._waiting.discard(session)
        session.apply_evaluation(
            evaluation.answer_loss, evaluation.actual_loss, evaluation.answer_sequence, evaluation.actual_sequence
        )
        self._reasons.pop(session, None)
        self._finish(session, self.judging.judge_settings.max_visits, self.judging.judges_with_compare)
        self.listener.changed(session)

    def _evaluation_failed(self, session: QuizSession, message: str) -> None:
        """Save the answer without losses, and tell why KataGo could not calculate them."""
        if session not in self._waiting:
            return
        self._waiting.discard(session)
        session.fail(SOURCE_KATAGO_ANSWER)
        session.fail(SOURCE_KATAGO_ACTUAL)
        self._reasons[session] = (REASON_FAILED, {"reason": message})
        self.save(session, None, False)
        self.listener.failed(REASON_FAILED, message)
        self.listener.changed(session)

    def _finish(self, session: QuizSession, max_visits: int | None, by_compare: bool) -> None:
        """Save a judged answer."""
        self.save(session, max_visits, by_compare)

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
            on_done=self.in_main(lambda sequence: self._predicted(session, move, sequence, source)),
            on_error=self.in_main(lambda _message: self._predicted(session, move, (), source)),
        )

    def _predicted(self, session: QuizSession, move: Move, sequence: tuple[Move, ...], source: str) -> None:
        """Add KataGo's sequence after a move, or mark it as failed."""
        if sequence:
            session.add_sequence(move, sequence, source)
        else:
            session.fail(source)
        self.listener.changed(session)

    def _ask_compare(self, session: QuizSession) -> None:
        """Ask the comparison model for the losses of the answer and the game move, and its best sequence."""
        session.expect(SOURCE_KATAGO_COMPARE)
        evaluate_moves(
            self.judging.compare_engine,
            session.problem.position,
            session.result.answer,
            session.problem.actual_move,
            self.judging.compare_settings,
            on_done=self.in_main(lambda evaluation: self._compared(session, evaluation)),
            on_error=self.in_main(lambda message: self._compare_failed(session, message)),
        )

    def _compared(self, session: QuizSession, evaluation: Evaluation) -> None:
        """Keep the comparison model's result and its best sequence."""
        session.apply_compare_evaluation(
            evaluation.answer_loss, evaluation.actual_loss, evaluation.best_sequence, evaluation.best_loss
        )
        self.listener.changed(session)

    def _compare_failed(self, session: QuizSession, message: str) -> None:
        """Mark the comparison model's sequence as failed, and tell why."""
        session.fail(SOURCE_KATAGO_COMPARE)
        self.listener.failed("notice_compare_line_failed", message)
        self.listener.changed(session)
