"""The areas of every position of a sequence after the answer, read shallowly (the board's colors).

After the answer, the board shows who owns each point at whatever move of the sequence is shown,
so that the user sees how the areas change move by move. These areas need not be exact: they are
read shallowly (see katago.quick_reading). The exact standing is calculated only at the last move
of a sequence (see quiz.standings), and its areas are shown there instead.
"""

from __future__ import annotations

from collections.abc import Callable

from kentogo.katago.estimate import played
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.quick_reading import QuickReadings
from kentogo.mistakes.problem import Variation
from kentogo.quiz.session import ANSWERED, QuizSession

Point = tuple[int, int]
Key = tuple[Variation, int]  # A sequence, and how many of its moves are played.


class QuickAreas:
    """The shallow areas of the positions of the sequences of one problem.

    Attributes:
        session: The session of the problem.
        readings: The readings so far (in the original direction and colors), by sequence and move.
    """

    def __init__(self, session: QuizSession, in_main: Callable[[Callable], Callable] = lambda function: function):
        """Start with none for a problem.

        Args:
            session: The session of the problem.
            in_main: Wraps a callback so that it runs in the screen's main thread.
        """
        self.session = session
        self.readings = QuickReadings(in_main)

    def shown(self) -> dict[Point, float] | None:
        """Return the areas of the shown position as the board is shown, once they are read (else None)."""
        key = self._shown_key()
        reading = self.readings.get(key) if key is not None else None
        if reading is None:
            return None
        transform, size = self.session.transform, self.session.problem.position.size
        sign = -1.0 if transform.swap_colors else 1.0
        return {transform.point(point, size): value * sign for point, value in reading.ownership.items()}

    def ask(self, engine: AnalysisEngine | None, wide_root_noise: float | None, on_change: Callable[[], None]) -> None:
        """Read the areas of the shown position if they are not known (after the answer; else nothing).

        Args:
            engine: KataGo with the main model, or None (then nothing is read).
            wide_root_noise: KaTrain's "wide_root_noise", or None for KataGo's own setting.
            on_change: Called (in the main thread) when the areas of a position have come.
        """
        key = self._shown_key()
        if key is None:
            return
        variation, step = key
        position = played(self.session.problem.position, variation.moves[:step])
        self.readings.ask(engine, key, position, wide_root_noise, on_change)

    def stop(self) -> None:
        """Stop the reading that has not been answered yet."""
        self.readings.stop()

    def _shown_key(self) -> Key | None:
        """Return the shown sequence and its number of moves shown, after the answer (else None)."""
        variation = self.session.variation
        if self.session.phase != ANSWERED or variation is None:
            return None
        return variation, self.session.replay_step
