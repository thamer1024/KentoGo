"""The territory and the standing at the end of a sequence of a problem (T), as KaTrain shows them.

The quiz keeps one SequenceStandings for the problem it shows. When a sequence that is not the
game's continuation is shown to its last move, T asks KataGo for the territory and the standing
there (with the model of the sequence: the comparison model for its own sequence, else the main
model), and for the game after the same number of moves, which is read from the SGF file. The
result is kept for the sequence, and shown until the user moves.

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
from kentogo.mistakes.problem import SOURCE_KATAGO_COMPARE, Variation
from kentogo.quiz.session import QuizSession
from kentogo.record.game_record import read_game_record

# Why the standing is not shown: keys of screen texts.
NOT_HERE = "estimate_not_here"  # No sequence is shown to its last move.
NO_ENGINE = "estimate_no_engine"  # The model of the sequence is not running.
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
        showing: True while the standing of the shown sequence is shown.
        busy: True while KataGo calculates one.
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
        self.showing = False
        self.busy = False

    def shown(self) -> Standing | None:
        """Return the standing of the shown sequence as the board is shown, while it is shown (else None)."""
        variation = self.session.sequence_at_end()
        if not self.showing or variation is None or variation not in self.found:
            return None
        return self.session.transform.standing(self.found[variation], self.session.problem.position.size)

    def hide(self) -> None:
        """Stop showing the standing (when the user moves)."""
        self.showing = False

    def toggle(self, models: Models, on_change: Changed, on_error: Failed) -> None:
        """Show or hide the standing of the shown sequence, calculating it the first time.

        Args:
            models: The main model and the comparison model (each None if it is not running).
            on_change: Called (in the main thread) when what is shown changes.
            on_error: Called with the key of a message and its reason, to tell the user.
        """
        if self.busy:
            return
        if self.showing:
            self.showing = False
            on_change()
            return
        self._show_or_estimate(models, on_change, on_error)

    def _show_or_estimate(self, models: Models, on_change: Changed, on_error: Failed) -> None:
        """Show the standing of the shown sequence if it is known, else ask KataGo for it."""
        variation = self.session.sequence_at_end()
        if variation is None:
            on_error(NOT_HERE, "")
            return
        if variation in self.found:
            self.showing = True
            on_change()
            return
        model = models.compare if variation.source == SOURCE_KATAGO_COMPARE else models.main
        if model is None:
            on_error(NO_ENGINE, "")
            return
        self._estimate(variation, model, on_change, on_error)

    def _estimate(self, variation: Variation, model: AnalysisModel, on_change: Changed, on_error: Failed) -> None:
        """Read the game and ask KataGo, in the background."""
        self.busy = True
        on_change()

        def done(standing: Standing) -> None:
            self.busy = False
            self.found[variation] = standing
            self.showing = self.session.sequence_at_end() == variation
            on_change()

        def failed(message: str) -> None:
            self.busy = False
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
