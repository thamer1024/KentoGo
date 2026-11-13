"""The territory and the standing at the end of each sequence of a problem, as KaTrain shows them.

After the answer, each sequence gets its standing by itself:
KataGo is asked about the position at the end of the sequence (with the main model), and about the game
after the same number
of moves, which is read from the SGF file (see prepare). Only the ends of the sequences are read, not
every move on the way, so it takes about one shallow reading per sequence (the visits of the territory
and the standing). The standing of the shown sequence is told while it is shown (shown), and its
territory is drawn on the board when the sequence is shown to its last move (at_end).

The SGF file is read in the background (background), and KataGo's answers come in its own
threads; both are passed through in_main before anything changes, as in quiz.quiz_run.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from kentogo.common import sgf
from kentogo.katago.estimate import Standing, estimate_standing, played
from kentogo.katago.evaluate import AnalysisModel, Models
from kentogo.mistakes.problem import Variation
from kentogo.quiz.session import ANSWERED, QuizSession
from kentogo.record.game_record import read_game_record

# Why a standing is not calculated: the key of a screen text.
FAILED = "estimate_failed"  # KataGo or the SGF file failed (with the reason).

Changed = Callable[[], None]
Failed = Callable[[str, str], None]  # The key of the text, and the reason ("" if there is none).


def in_background(work: Callable[[], None]) -> None:
    """Run work in a background thread."""
    threading.Thread(target=work, daemon=True).start()


class SequenceStandings:
    """The territory and the standing at the ends of the sequences of one problem.

    Attributes:
        session: The session of the problem.
        found: The standings calculated so far, by sequence.
        pending: The sequences whose standing KataGo is calculating.
        failed: The sequences whose standing could not be calculated (they are not asked again).
    """

    def __init__(
        self,
        session: QuizSession,
        in_main: Callable[[Callable], Callable] = lambda function: function,
        background: Callable[[Callable[[], None]], None] = in_background,
    ):
        """Start with none for a problem.

        Args:
            session: The session of the problem.
            in_main: Wraps a callback so that it runs in the screen's main thread.
            background: Runs the reading of the SGF file and the queries (tests run them at once).
        """
        self.session = session
        self.in_main = in_main
        self.background = background
        self.found: dict[Variation, Standing] = {}
        self.pending: set[Variation] = set()
        self.failed: set[Variation] = set()

    @property
    def busy(self) -> bool:
        """True while KataGo calculates the standing of the shown sequence."""
        return self.session.variation in self.pending

    def shown(self) -> Standing | None:
        """Return the standing at the end of the shown sequence as the board is shown, once it is known (else None)."""
        variation = self.session.variation
        if self.session.phase != ANSWERED or variation is None or variation not in self.found:
            return None
        return self.session.transform.standing(self.found[variation], self.session.problem.position.size)

    def at_end(self) -> Standing | None:
        """Return the standing of the shown sequence while it is shown to its last move (its territory is drawn)."""
        return self.shown() if self.session.sequence_at_end() is not None else None

    def prepare(self, models: Models, on_change: Changed, on_error: Failed) -> None:
        """Ask KataGo for the standing of each sequence that has none yet (after the answer; else nothing).

        Args:
            models: The main model (None if it is not running: then the
                sequences of that model get no standing).
            on_change: Called (in the main thread) when a standing has come.
            on_error: Called with the key of a message and its reason, to tell the user.
        """
        if self.session.phase != ANSWERED:
            return
        for variation in self._sequences():
            if variation in self.found or variation in self.pending or variation in self.failed:
                continue
            if models.main is not None:
                self._estimate(variation, models.main, on_change, on_error)

    def _sequences(self) -> list[Variation]:
        """Return the sequences that get a standing: those with moves."""
        return [
            choice.variation
            for choice in self.session.choices
            if choice.variation is not None and choice.variation.moves
        ]

    def _estimate(self, variation: Variation, model: AnalysisModel, on_change: Changed, on_error: Failed) -> None:
        """Read the game and ask KataGo, in the background."""
        self.pending.add(variation)

        def done(standing: Standing) -> None:
            self.pending.discard(variation)
            self.found[variation] = standing
            on_change()

        def failed(message: str) -> None:
            self.pending.discard(variation)
            self.failed.add(variation)
            on_change()
            on_error(FAILED, message)

        self.background(lambda: self._ask(variation, model, self.in_main(done), self.in_main(failed)))

    def _ask(
        self,
        variation: Variation,
        model: AnalysisModel,
        done: Callable[[Standing], None],
        failed: Callable[[str], None],
    ) -> None:
        """Read the game from the SGF file, then send the queries (failed is told why if either fails)."""
        problem, moves = self.session.problem, variation.moves
        try:
            record = read_game_record(sgf.load_game(Path(problem.sgf_path)))
            game = record.position_after(problem.move_number - 1 + len(moves))
            end = played(problem.position, moves)
            estimate_standing(model.engine, end, game, moves[0].color, model.settings, done, failed)
        except Exception as error:  # The file cannot be read, or KataGo cannot be started.
            failed(str(error) or type(error).__name__)
