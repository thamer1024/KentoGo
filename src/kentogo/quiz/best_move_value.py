"""What the best move of a problem does, read by KataGo after the answer (see katago.move_value).

After the answer (right or wrong), KataGo reads the problem position after the best move and after a
pass, once for each problem. The result is shown with what the best move does on the board (see
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
        self._stopped = False

    def ask(self, engine: AnalysisEngine | None, settings: EvaluationSettings, on_change: Callable[[], None]) -> None:
        """Ask KataGo once, after the answer (nothing without KataGo, a best move or an answer).

        Args:
            engine: KataGo with the main model, or None.
            settings: The visits (estimate_visits) and the noise.
            on_change: Called (in the main thread) when the value has come.
        """
        problem = self.session.problem
        if self._asked or engine is None or problem.best_move is None or self.session.phase != ANSWERED:
            return
        self._asked = True
        try:
            read_move_value(
                engine,
                problem.position,
                problem.best_move,
                settings.estimate_visits,
                settings.wide_root_noise,
                self._in_main(lambda value: self._keep(value, on_change)),
                self._in_main(lambda _message: None),  # Then only what the stones tell is shown.
            )
        except IllegalMoveError:
            return

    def stop(self) -> None:
        """Drop the value that has not come yet (the problem is left)."""
        self._stopped = True

    def _keep(self, value: MoveValue, on_change: Callable[[], None]) -> None:
        """Keep the value and tell the screen, unless the problem was left."""
        if self._stopped:
            return
        self.value = value
        on_change()
