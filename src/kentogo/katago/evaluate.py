"""Calculate the points lost by the answer and by the game move, with KataGo.

Both moves are calculated under the same conditions (the same KataGo, model and
number of visits), so that they can be compared fairly. Three positions are
analyzed: before the moves, after the answer, and after the game move.
KataGo's predicted sequences after the answer and after the game move are also
kept, so that the user can see how each move is punished (or works out).

This module does not depend on KataGoProcess. It only needs an object with a
query() method (AnalysisEngine), so tests can use a fake engine.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from kentogo.common.types import Move, Position, moves_from_gtp, opponent
from kentogo.katago.queries import best_move_score, best_sequence, points_lost, position_query, root_score


class AnalysisEngine(Protocol):
    """What this module needs from a KataGo engine (KataGoProcess has it)."""

    def query(self, request: dict, callback: Callable[[dict], None]) -> str:
        """Send a query, and call callback with each answer."""
        ...


@dataclass(frozen=True)
class Evaluation:
    """The points lost by the answer and by the game move, under the same conditions.

    Attributes:
        answer_loss: Points lost by the answer.
        actual_loss: Points lost by the move played in the game.
        answer_sequence: KataGo's predicted moves after the answer, starting with the opponent's reply.
        actual_sequence: KataGo's predicted moves after the game move, starting with the opponent's reply.
        best_sequence: KataGo's best sequence in the problem position, starting with its best move.
        best_loss: Points lost by KataGo's best move (about 0, or a little more or less, because
            the score after one move is not exactly the score of the position), or None if not known.
    """

    answer_loss: float
    actual_loss: float
    answer_sequence: tuple[Move, ...] = ()
    actual_sequence: tuple[Move, ...] = ()
    best_sequence: tuple[Move, ...] = ()
    best_loss: float | None = None


@dataclass(frozen=True)
class EvaluationSettings:
    """How KataGo analyzes the positions.

    Attributes:
        max_visits: How many positions KataGo reads for each analysis.
        wide_root_noise: KaTrain's "wide_root_noise" setting, or None to use KataGo's own setting.
        estimate_visits: How many positions KataGo reads for the territory and the standing (see katago.estimate).
    """

    max_visits: int = 500
    wide_root_noise: float | None = None
    estimate_visits: int = 100


def evaluate_moves(
    engine: AnalysisEngine,
    position: Position,
    answer: Move,
    actual: Move,
    settings: EvaluationSettings,
    on_done: Callable[[Evaluation], None],
    on_error: Callable[[str], None],
) -> None:
    """Ask KataGo for the points lost by the answer and by the game move.

    This returns at once. When all three analyses are done, on_done is called;
    if one of them fails, on_error is called instead. Exactly one of them is
    called, once, in the engine's background thread.

    Args:
        engine: The KataGo engine.
        position: The problem position (before the moves).
        answer: The user's answer.
        actual: The move played in the game.
        settings: How KataGo analyzes the positions.
        on_done: Called with the result.
        on_error: Called with an error message.
    """
    collector = _Collector(answer.color, actual.color, on_done, on_error)
    for key, extra_moves in (("before", ()), ("answer", (answer,)), ("actual", (actual,))):
        request = position_query(position, extra_moves, settings.max_visits, settings.wide_root_noise)
        engine.query(request, collector.receiver(key))


def predict_after(
    engine: AnalysisEngine,
    position: Position,
    move: Move,
    settings: EvaluationSettings,
    on_done: Callable[[tuple[Move, ...]], None],
    on_error: Callable[[str], None],
) -> None:
    """Ask KataGo for its predicted sequence after one move (one analysis).

    This is used when the loss of the move is already known from the SGF file,
    but the user wants to see what happens after it. This returns at once, and
    on_done or on_error is called once, in the engine's background thread.

    Args:
        engine: The KataGo engine.
        position: The problem position (before the move).
        move: The move.
        settings: How KataGo analyzes the position.
        on_done: Called with the predicted moves after the move, starting with the opponent's reply.
        on_error: Called with an error message.
    """

    def receive(answer: dict) -> None:
        """Pass the sequence of the final answer, or the error, to the caller."""
        if answer.get("isDuringSearch"):
            return
        if "error" in answer:
            on_error(f"KataGo could not analyze the position: {answer['error']}")
        else:
            on_done(moves_from_gtp(best_sequence(answer), opponent(move.color)))

    request = position_query(position, (move,), settings.max_visits, settings.wide_root_noise)
    engine.query(request, receive)


def predict_best(
    engine: AnalysisEngine,
    position: Position,
    settings: EvaluationSettings,
    on_done: Callable[[tuple[Move, ...]], None],
    on_error: Callable[[str], None],
) -> None:
    """Ask KataGo for its best sequence in a position, starting with the best move (one analysis).

    This returns at once, and on_done or on_error is called once, in the engine's background thread.

    Args:
        engine: The KataGo engine.
        position: The position.
        settings: How KataGo analyzes the position.
        on_done: Called with the best sequence (empty if KataGo gave none).
        on_error: Called with an error message.
    """

    def receive(answer: dict) -> None:
        """Pass the sequence of the final answer, or the error, to the caller."""
        if answer.get("isDuringSearch"):
            return
        if "error" in answer:
            on_error(f"KataGo could not analyze the position: {answer['error']}")
        else:
            on_done(moves_from_gtp(best_sequence(answer), position.next_color))

    engine.query(position_query(position, (), settings.max_visits, settings.wide_root_noise), receive)


@dataclass(frozen=True)
class AnalysisModel:
    """KataGo with one model, for a screen that asks it only when the user wants.

    Attributes:
        engine: The engine (one query at a time).
        settings: How it analyzes the positions (its own number of visits).
    """

    engine: AnalysisEngine
    settings: EvaluationSettings


@dataclass(frozen=True)
class Models:
    """The models that the screen that shows a game can ask.

    Attributes:
        main: KataGo with the main model (for the territory and the standing), or None.
        compare: KataGo with the comparison model, or None.
    """

    main: AnalysisModel | None = None
    compare: AnalysisModel | None = None


class _Collector:
    """Collects the three analyses, and calls on_done or on_error once."""

    def __init__(
        self,
        answer_color: str,
        actual_color: str,
        on_done: Callable[[Evaluation], None],
        on_error: Callable[[str], None],
    ):
        """Start with no analyses.

        Args:
            answer_color: Color of the answer.
            actual_color: Color of the game move.
            on_done: Called with the result.
            on_error: Called with an error message.
        """
        self.colors = {"answer": answer_color, "actual": actual_color}
        self.on_done = on_done
        self.on_error = on_error
        self.scores: dict[str, float] = {}
        self.sequences: dict[str, tuple[str, ...]] = {}
        self.best_score: float | None = None  # The score after the best move in the problem position.
        self.finished = False
        self.lock = threading.Lock()

    def receiver(self, key: str) -> Callable[[dict], None]:
        """Return the callback for the analysis with the given key ("before", "answer" or "actual")."""
        return lambda answer: self._receive(key, answer)

    def _receive(self, key: str, answer: dict) -> None:
        """Keep the score of one analysis, and finish when all three are here or one failed."""
        if answer.get("isDuringSearch"):
            return
        with self.lock:
            if self.finished:
                return
            try:
                self.scores[key] = root_score(answer)
                self.sequences[key] = best_sequence(answer)
                if key == "before":
                    self.best_score = best_move_score(answer)
            except ValueError as error:
                self.finished = True
                failure = str(error)
            else:
                if len(self.scores) < 3:
                    return
                self.finished = True
                failure = None
        if failure is not None:
            self.on_error(failure)
        else:
            self.on_done(self._evaluation())

    def _evaluation(self) -> Evaluation:
        """Calculate the losses from the three scores."""
        before = self.scores["before"]
        return Evaluation(
            answer_loss=points_lost(self.colors["answer"], before, self.scores["answer"]),
            actual_loss=points_lost(self.colors["actual"], before, self.scores["actual"]),
            answer_sequence=self._sequence_after("answer"),
            actual_sequence=self._sequence_after("actual"),
            # The answer is played by the player to move, so its color is the color of the best move.
            best_sequence=moves_from_gtp(self.sequences["before"], self.colors["answer"]),
            best_loss=None if self.best_score is None else points_lost(self.colors["answer"], before, self.best_score),
        )

    def _sequence_after(self, key: str) -> tuple[Move, ...]:
        """Return KataGo's predicted moves after the answer or the game move, as moves."""
        return moves_from_gtp(self.sequences[key], opponent(self.colors[key]))
