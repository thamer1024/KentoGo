"""What KataGo calculates for the screen that shows a game (no screen).

The territory and the standing at the end of a sequence (T) are asked with the main model when the
user wants them, and kept for the game that is open.

The screen tells which game is open (open), and gives each end of a sequence a key of its own
(the place on the screen). KataGo answers in its own threads: each answer is passed through
in_main, and then the listener is told. An answer for a game that is no longer open is dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Protocol

from kentogo.katago.estimate import Standing, estimate_standing, played
from kentogo.katago.evaluate import Models
from kentogo.mistakes.problem import Variation
from kentogo.record.game_record import GameRecord

# Keys of the screen texts that tell why something is not calculated.
NO_ENGINE = "estimate_no_engine"  # The main model is not running.
ESTIMATE_FAILED = "estimate_failed"  # The territory could not be calculated (with the reason).


class AnalysesListener(Protocol):
    """What the screen is told (always in its main thread, see in_main)."""

    def estimated(self, key: Hashable) -> None:
        """The territory and the standing at the end of a sequence of the open game have arrived."""

    def failed(self, text_key: str, reason: str) -> None:
        """Something could not be calculated: the key of the message, and why ("" if there is no reason)."""


@dataclass
class GameAnalyses:
    """KataGo's sequences and standings for the open game.

    Attributes:
        models: The main model (None if it is not running).
        listener: Told what has arrived or failed.
        in_main: Wraps a callback of KataGo so that it runs in the screen's main thread.
        record: The open game, or None.
        standings: The territory and the standing at the ends of sequences, by the screen's key.
        estimating: True while the territory and the standing are calculated.
    """

    models: Models
    listener: AnalysesListener
    in_main: Callable[[Callable], Callable] = lambda function: function
    record: GameRecord | None = field(default=None, init=False)
    standings: dict[Hashable, Standing] = field(default_factory=dict, init=False)
    estimating: bool = field(default=False, init=False)

    def open(self, record: GameRecord) -> None:
        """Start again for another game: what was found for the game before is forgotten."""
        self.record = record
        self.standings = {}

    @property
    def busy(self) -> bool:
        """True while KataGo calculates something for the screen."""
        return self.estimating

    def estimate(self, key: Hashable, position: int, variation: Variation) -> None:
        """Ask for the territory and the standing at the end of a sequence played in place of the move of a position.

        The game after the same number of moves is analyzed too, to tell how much better the sequence is.
        """
        model = self.models.main
        if model is None:
            self.listener.failed(NO_ENGINE, "")
            return
        record, moves = self.record, variation.moves
        self.estimating = True

        def done(standing: Standing) -> None:
            self._estimated(record, key, standing)

        def failed(message: str) -> None:
            self._estimate_failed(message)

        try:
            end = played(record.position_before(position), moves)
            game = record.position_after(position - 1 + len(moves))
            estimate_standing(
                model.engine, end, game, moves[0].color, model.settings, self.in_main(done), self.in_main(failed)
            )
        except Exception as error:  # For example, KataGo cannot be started.
            failed(str(error) or type(error).__name__)

    def _estimated(self, record: GameRecord, key: Hashable, standing: Standing) -> None:
        """Keep the territory and the standing, if the game is still open."""
        self.estimating = False
        if record is not self.record:
            return
        self.standings[key] = standing
        self.listener.estimated(key)

    def _estimate_failed(self, message: str) -> None:
        """Tell that the territory and the standing could not be calculated."""
        self.estimating = False
        self.listener.failed(ESTIMATE_FAILED, message)
