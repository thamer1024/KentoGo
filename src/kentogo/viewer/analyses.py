"""What KataGo calculates for the screen that shows a game (no screen).

Two things are asked when the user wants them, and kept for the game that is open:

- the comparison model's best sequence in the position before a move (Tab after the last
  sequence of the move), one move at a time;
- the territory and the standing at the end of a sequence (T), with the model of the sequence:
  the comparison model for its own sequences, else the main model.

The screen tells which game is open (open), and gives each end of a sequence a key of its own
(the place on the screen). KataGo answers in its own threads: each answer is passed through
in_main, and then the listener is told. An answer for a game that is no longer open is dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Protocol

from kentogo.katago.estimate import Standing, estimate_standing, played
from kentogo.katago.evaluate import AnalysisModel, Models, predict_best
from kentogo.mistakes.problem import SOURCE_KATAGO_COMPARE, Variation
from kentogo.record.game_record import GameRecord

# Keys of the screen texts that tell why something is not calculated.
NO_SEQUENCE = "compare_no_sequence"  # The comparison model gave no sequence.
COMPARE_FAILED = "notice_compare_line_failed"  # The comparison model failed (with the reason).
NO_ENGINE = "estimate_no_engine"  # The model of the sequence is not running.
ESTIMATE_FAILED = "estimate_failed"  # The territory could not be calculated (with the reason).


class AnalysesListener(Protocol):
    """What the screen is told (always in its main thread, see in_main)."""

    def compared(self, position: int) -> None:
        """The comparison model's sequence at a position of the open game has arrived."""

    def estimated(self, key: Hashable) -> None:
        """The territory and the standing at the end of a sequence of the open game have arrived."""

    def failed(self, text_key: str, reason: str) -> None:
        """Something could not be calculated: the key of the message, and why ("" if there is no reason)."""


@dataclass
class GameAnalyses:
    """KataGo's sequences and standings for the open game.

    Attributes:
        models: The main model and the comparison model (each None if it is not running).
        listener: Told what has arrived or failed.
        in_main: Wraps a callback of KataGo so that it runs in the screen's main thread.
        record: The open game, or None.
        lines: The comparison model's sequences of the open game, by position.
        standings: The territory and the standing at the ends of sequences, by the screen's key.
        analyzing: The position that the comparison model is analyzing, or None.
        estimating: True while the territory and the standing are calculated.
    """

    models: Models
    listener: AnalysesListener
    in_main: Callable[[Callable], Callable] = lambda function: function
    record: GameRecord | None = field(default=None, init=False)
    lines: dict[int, Variation] = field(default_factory=dict, init=False)
    standings: dict[Hashable, Standing] = field(default_factory=dict, init=False)
    analyzing: int | None = field(default=None, init=False)
    estimating: bool = field(default=False, init=False)

    def open(self, record: GameRecord) -> None:
        """Start again for another game: what was found for the game before is forgotten."""
        self.record = record
        self.lines = {}
        self.standings = {}

    @property
    def busy(self) -> bool:
        """True while KataGo calculates something for the screen."""
        return self.analyzing is not None or self.estimating

    def can_compare(self, position: int) -> bool:
        """True if the comparison model can be asked for the move of a position (it runs, and has no sequence there)."""
        record = self.record
        return (
            self.models.compare is not None
            and record is not None
            and position not in self.lines
            and record.move_at(position) is not None
        )

    def compare(self, position: int) -> None:
        """Ask the comparison model for its best sequence in the position before the move of a position."""
        record, model = self.record, self.models.compare
        self.analyzing = position

        def done(moves: tuple) -> None:
            self._compared(record, position, moves)

        def failed(message: str) -> None:
            self._compare_failed(message)

        try:
            before = record.position_before(position)
            predict_best(model.engine, before, model.settings, self.in_main(done), self.in_main(failed))
        except Exception as error:  # For example, KataGo cannot be started.
            failed(str(error) or type(error).__name__)

    def estimate(self, key: Hashable, position: int, variation: Variation) -> None:
        """Ask for the territory and the standing at the end of a sequence played in place of the move of a position.

        The game after the same number of moves is analyzed too, to tell how much better the sequence is.
        """
        model = self._model_for(variation)
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

    def _model_for(self, variation: Variation) -> AnalysisModel | None:
        """Return the model of a sequence: the comparison model for its own sequences, else the main model."""
        return self.models.compare if variation.source == SOURCE_KATAGO_COMPARE else self.models.main

    def _compared(self, record: GameRecord, position: int, moves: tuple) -> None:
        """Keep the comparison model's sequence, if the game is still open."""
        self.analyzing = None
        if record is not self.record:
            return  # Another game was opened meanwhile.
        if not moves:
            self.listener.failed(NO_SEQUENCE, "")
            return
        self.lines[position] = Variation(tuple(moves), SOURCE_KATAGO_COMPARE)
        self.listener.compared(position)

    def _compare_failed(self, message: str) -> None:
        """Tell that the comparison model could not analyze the move."""
        self.analyzing = None
        self.listener.failed(COMPARE_FAILED, message)

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
