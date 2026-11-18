"""What the best move of a problem does, read by KataGo after the answer (see katago.move_value).

The best move is the one that the session shows (see QuizSession.best_move). After the answer (right or wrong)
and when the best move is known, KataGo reads the problem position after it and after a pass, once for each problem. The result is shown with what the best move does on the board (see
common.tactics): how many points leaving it loses, whether it is urgent (急場) or a big point (大場),
and the stones it kills or saves. Nothing is read before the answer, or for a problem without a best move.
"""

from __future__ import annotations

from collections.abc import Callable

from kentogo.common.board import IllegalMoveError
from kentogo.katago.evaluate import AnalysisEngine, EvaluationSettings
from kentogo.katago.move_value import MoveValue, read_move_value
from kentogo.quiz.session import ANSWERED, QuizSession


class BestMoveValue:
    """The value of the best move of one problem, read once after the answer.

    Attributes:
        session: The session of the problem.
        value: The value once KataGo has read it, else None.
    """

    def __init__(self, session: QuizSession, in_main: Callable[[Callable], Callable] = lambda function: function):
        """Start without a value.

        Args:
            session: The session of the problem.
            in_main: Wraps a callback so that it runs in the screen's main thread.
        """
        self.session = session
        self.value: MoveValue | None = None
        self._in_main = in_main
        self._asked = False
        self._failed = False
        self._stopped = False

    @property
    def running(self) -> bool:
        """True while KataGo is reading the value (asked, and neither come nor failed, nor the problem left)."""
        return self._asked and self.value is None and not self._failed and not self._stopped

    def ask(self, engine: AnalysisEngine | None, settings: EvaluationSettings, on_change: Callable[[], None]) -> None:
        """Ask KataGo once, after the answer (nothing without KataGo, a best move or an answer).

        Args:
            engine: KataGo with the main model, or None.
            settings: The visits (estimate_visits) and the noise.
            on_change: Called (in the main thread) when the value has come.
        """
        problem, best = self.session.problem, self.session.best_move
        if self._asked or engine is None or best is None or self.session.phase != ANSWERED:
            return  # While the best move is being calculated, it is asked again when it has come.
        self._asked = True
        try:
            read_move_value(
                engine,
                problem.position,
                best,
                settings.estimate_visits,
                settings.wide_root_noise,
                self._in_main(lambda value: self._keep(value, on_change)),
                self._in_main(lambda _message: self._fail(on_change)),  # Then only what the stones tell is shown.
            )
        except IllegalMoveError:
            self._failed = True  # Nothing is read.

    def stop(self) -> None:
        """Drop the value that has not come yet (the problem is left)."""
        self._stopped = True

    def _fail(self, on_change: Callable[[], None]) -> None:
        """Tell the screen that there will be no value, unless the problem was left."""
        if self._stopped:
            return
        self._failed = True
        on_change()

    def _keep(self, value: MoveValue, on_change: Callable[[], None]) -> None:
        """Keep the value and tell the screen, unless the problem was left."""
        if self._stopped:
            return
        self.value = value
        on_change()
