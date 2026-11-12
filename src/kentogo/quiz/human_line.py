"""KataGo's sequences of a problem, with the opponent's replies of a human of its rank.

KataGo's own sequence has the opponent's best replies, which are much stronger than the opponent's
real moves (often KaTrain's human-like AI), so the sequence often ends worse for the user than the
game did. So the sequence is made again move by move: the opponent's moves are the moves that a human
of the opponent's rank would most likely play (see katago.human_moves), as KaTrain's human-like AI
plays them. The user's moves are those of a human too (my_profile: the user's rank, else the opponent's),
except in the comparison model's sequence, where the comparison model plays its best moves. Without the
opponent's rank (profile ""), the opponent plays the best moves of the sequence's model too.

A sequence can be made longer than KataGo's own one (see Extension): the comparison model reads with few
visits, so its own sequence is often much shorter than KaTrain's. The moves after KataGo's own length are
added only while the time limit has not passed, so that the user does not wait long. Otherwise the
sequence is as long as KataGo's own sequence. It ends at a pass.

The rank is found elsewhere (see kentogo.opponent_rank).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from kentogo.common.types import Move, Position, opponent
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import human_query, most_likely_move
from kentogo.katago.queries import best_sequence, position_query


@dataclass(frozen=True)
class PlayerRanks:
    """The ranks of the players of a problem's game, such as "10k" ("" if not known; see kentogo.opponent_rank).

    Attributes:
        mine: The user's rank.
        theirs: The opponent's rank (the user's rank when the opponent's is not known).
    """

    mine: str = ""
    theirs: str = ""


@dataclass(frozen=True)
class Extension:
    """How far a sequence is made longer than KataGo's own one.

    Attributes:
        length: The number of moves aimed at.
        seconds: No move is added after KataGo's own length once this many seconds have passed since the start.
        clock: Returns the time in seconds (time.monotonic; tests give their own).
    """

    length: int
    seconds: float
    clock: Callable[[], float] = field(default=time.monotonic, compare=False)


@dataclass(frozen=True)
class LineEngines:
    """What the sequence is made with.

    Attributes:
        best: KataGo for the best moves of a side without a profile (the main KataGo, or the comparison model).
        human: KataGo with the human-like model (the main KataGo), for the moves of a side with a profile.
        visits: The visits of each best move.
        wide_root_noise: KaTrain's "wide_root_noise", or None for KataGo's own setting.
        profile: KataGo's humanSLProfile of the opponent's rank (see katago.human_moves.human_profile), or ""
            (then the opponent plays best's best moves: the strongest replies).
        my_profile: KataGo's humanSLProfile of the user's rank, or "" (then the user plays best's best moves).
    """

    best: AnalysisEngine
    human: AnalysisEngine
    visits: int
    wide_root_noise: float | None
    profile: str
    my_profile: str = ""


def build_line(
    engines: LineEngines,
    position: Position,
    first_line: tuple[Move, ...],
    on_done: Callable[[tuple[Move, ...]], None],
    on_error: Callable[[str], None],
    extension: Extension | None = None,
) -> None:
    """Make the sequence from the first move of KataGo's own sequence, one query for each move.

    Args:
        engines: What the sequence is made with.
        position: The problem position.
        first_line: KataGo's own sequence, from the user's move (the answer, the game move or the best move).
        on_done: Called with the sequence (in KataGo's thread).
        on_error: Called with what went wrong (in KataGo's thread).
        extension: How far the sequence is made longer than first_line, or None (as long as first_line).
    """
    if not first_line:
        on_done(())
        return
    length = _Length(len(first_line), extension or Extension(len(first_line), 0.0))
    maker = _LineMaker(engines, position, length, first_line[0].color, on_done, on_error)
    # When both sides play the best moves, KataGo's own sequence is kept as it is, and only made longer.
    kept = first_line if not engines.profile and not engines.my_profile else first_line[:1]
    maker.moves = kept[:-1]
    maker.add(kept[-1])


class _Length:
    """Tells when a sequence is complete: at KataGo's own length, or later while the time limit has not passed."""

    def __init__(self, own: int, extension: Extension):
        """Start the time now."""
        self.own, self.extension = own, extension
        self.deadline = extension.clock() + extension.seconds

    def complete(self, moves: int) -> bool:
        """True if a sequence of this many moves is complete."""
        if moves < self.own:
            return False
        return moves >= self.extension.length or self.extension.clock() > self.deadline


class _LineMaker:
    """Adds the moves of a sequence one after another, each when KataGo has answered."""

    def __init__(self, engines: LineEngines, position: Position, length: _Length, my_color: str, on_done, on_error):
        """Keep what the sequence is made with (see build_line)."""
        self.engines, self.position, self.length, self.my_color = engines, position, length, my_color
        self.on_done, self.on_error = on_done, on_error
        self.moves: tuple[Move, ...] = ()

    def add(self, move: Move) -> None:
        """Add a move, and ask for the next one unless the sequence is complete."""
        self.moves += (move,)
        if self.length.complete(len(self.moves)) or move.is_pass:
            self.on_done(self.moves)
            return
        color = opponent(move.color)
        profile = self.engines.profile if color != self.my_color else self.engines.my_profile
        if profile:
            self._ask_human(color, profile)
        else:
            self._ask_best(color)

    def _ask_best(self, color: str) -> None:
        """Ask for the best move of the sequence's model."""
        query = position_query(self.position, self.moves, self.engines.visits, self.engines.wide_root_noise)
        self.engines.best.query(query, self._receiver(lambda answer: self._best_move(answer, color)))

    def _ask_human(self, color: str, profile: str) -> None:
        """Ask for the move that a human of a profile would most likely play next."""
        query = human_query(self.position, self.moves, profile)
        self.engines.human.query(
            query, self._receiver(lambda answer: most_likely_move(answer, self.position.size, color))
        )

    def _receiver(self, read: Callable[[dict], Move | None]) -> Callable[[dict], None]:
        """Return the callback that reads the next move from KataGo's final answer, and adds it."""

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                move = read(answer)
            except ValueError as error:
                self.on_error(str(error))
                return
            if move is None:
                self.on_done(self.moves)
            else:
                self.add(move)

        return receive

    @staticmethod
    def _best_move(answer: dict, color: str) -> Move | None:
        """Return KataGo's best move in its answer (None if it has none).

        Raises:
            ValueError: If the answer is an error.
        """
        if "error" in answer:
            raise ValueError(f"KataGo could not analyze the position: {answer['error']}")
        points = best_sequence(answer)
        return Move.from_gtp(points[0], color) if points else None
