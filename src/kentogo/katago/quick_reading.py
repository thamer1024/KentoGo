"""Shallow readings of positions with their areas, one at a time, for showing the areas move by move.

A screen that lets the user go through a game or a sequence shows who owns each point at every
move. These readings need not be exact: KataGo reads each position with QUICK_VISITS visits only
(about a tenth of a second with a GPU). A shallow reading is right in calm positions, though it can
be wrong where a group's life or a fight is not settled; the exact standing is read elsewhere, with
more visits, where the screen needs it (see katago.estimate).

One position is read at a time: when the user moves on before KataGo has answered, the reading is
stopped (KataGo's "terminate", when the engine has it), and the new position is read. Each reading
is kept by the key that the screen gives it, so going back and forth shows it at once. KataGo's
answers are passed through in_main before anything changes.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass

from kentogo.common.types import Position
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.queries import ownership_map, position_query, root_score, with_ownership

QUICK_VISITS = 48  # The visits of the areas of each position (not exact, but quick).

Point = tuple[int, int]


@dataclass(frozen=True)
class QuickReading:
    """A shallow reading of a position.

    Attributes:
        ownership: The owner of each point, from black's side (1: black, -1: white).
        lead: Black's score lead (not exact).
    """

    ownership: dict[Point, float]
    lead: float


class QuickReadings:
    """The shallow readings of the positions that a screen shows, by the screen's keys."""

    def __init__(self, in_main: Callable[[Callable], Callable] = lambda function: function):
        """Start with none.

        Args:
            in_main: Wraps a callback so that it runs in the screen's main thread.
        """
        self.in_main = in_main
        self.found: dict[Hashable, QuickReading] = {}
        self._failed: set[Hashable] = set()  # Positions that KataGo could not read (not asked again).
        self._asking: Hashable | None = None
        self._query_id = ""
        self._engine: AnalysisEngine | None = None

    def get(self, key: Hashable) -> QuickReading | None:
        """Return the reading of a position, once it has come (else None)."""
        return self.found.get(key)

    def ask(
        self,
        engine: AnalysisEngine | None,
        key: Hashable,
        position: Position,
        wide_root_noise: float | None,
        on_change: Callable[[], None],
    ) -> None:
        """Read a position if it is not known; a reading of another position not answered yet is stopped first.

        Args:
            engine: KataGo, or None (then nothing is read).
            key: The screen's key of the position.
            position: The position.
            wide_root_noise: KaTrain's "wide_root_noise", or None for KataGo's own setting.
            on_change: Called (in the main thread) when the reading has come.
        """
        if engine is None or key in self.found or key in self._failed or key == self._asking:
            return
        self.stop()
        query = with_ownership(position_query(position, (), QUICK_VISITS, wide_root_noise))
        self._asking, self._engine = key, engine
        self._query_id = engine.query(query, self.in_main(self._receiver(key, position.size, on_change)))

    def stop(self) -> None:
        """Stop the reading that has not been answered yet (its answer is then dropped)."""
        if self._asking is None:
            return
        terminate = getattr(self._engine, "terminate", None)
        if terminate is not None and self._query_id:
            terminate(self._query_id)
        self._asking, self._query_id = None, ""

    def _receiver(self, key: Hashable, size: int, on_change: Callable[[], None]) -> Callable[[dict], None]:
        """Return the callback of the reading of one position (in the main thread)."""

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch") or self._asking != key:
                return  # A report on the way, or the answer of a reading that was stopped.
            self._asking, self._query_id = None, ""
            try:
                self.found[key] = QuickReading(ownership_map(answer, size), root_score(answer))
            except ValueError:  # An error, or no areas: nothing is shown for this position.
                self._failed.add(key)
                return
            on_change()

        return receive
