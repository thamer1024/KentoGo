"""KataGo's sequences of a problem, made again move by move with the moves of a human of a rank.

KataGo's own sequence has the best moves of both sides, which are much stronger than the user's real
moves. So the sequence is made again move by move: a side with a profile (my_profile for the user,
profile for the opponent) plays the move that a human of that rank would most likely play (see
katago.human_moves), as KaTrain's human-like AI plays it; a side without one plays KataGo's best move.
The quiz makes two sequences with the profiles of both players: one after the user's answer, and one from
the problem position, in which the user plays the best of the moves that a human of the user's rank may
play (see LineEngines.my_visits).

A sequence can be made longer than KataGo's own one (see Extension), so that the sequences of a problem
are as long as the game's own moves after the problem. No clock cuts a sequence short: how long it takes
depends on the computer, so each reading has the user's own time limit instead (LineEngines.max_time).
Without an Extension the sequence is as long as KataGo's own sequence. It ends at a pass.

The rank is found elsewhere (see kentogo.opponent_rank).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from kentogo.common.types import Move, Position, opponent
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import candidate_moves, human_query, most_likely_move
from kentogo.katago.queries import best_sequence, position_query
from kentogo.quiz.natural_move import choose_move


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
        length: The number of moves aimed at. How long it takes is not limited by a time: each reading of KataGo
            has its own limit (LineEngines.max_time, the user's setting), so a slow computer reads less.
    """

    length: int


@dataclass(frozen=True)
class LineEngines:
    """What the sequence is made with.

    Attributes:
        best: KataGo for the best moves of a side without a profile (the main KataGo).
        human: KataGo with the human-like model (the main KataGo), for the moves of a side with a profile.
        visits: The visits of each best move.
        wide_root_noise: KaTrain's "wide_root_noise", or None for KataGo's own setting.
        profile: KataGo's humanSLProfile of the opponent's rank (see katago.human_moves.human_profile), or ""
            (then the opponent plays best's best moves: the strongest replies).
        my_profile: KataGo's humanSLProfile of the user's rank, or "" (then the user plays best's best moves).
        my_visits: When it is more than 0, the user plays a natural and strong move among the moves that a human of
            my_profile may play, not the most likely one (see quiz.natural_move): best reads the candidates with
            this many visits.
        first_visits: The visits for the user's first move of a sequence made from the problem position (0: my_visits).
        max_time: The most seconds of each reading of KataGo for a move (KataGo's maxTime, the user's setting
            "max_time"); 0 means no limit.
        log: Called with a record (a dict) about each move that the user's choice was made for.
    """

    best: AnalysisEngine
    human: AnalysisEngine
    visits: int
    wide_root_noise: float | None
    profile: str
    my_profile: str = ""
    my_visits: int = 0
    first_visits: int = 0
    max_time: float = 0.0
    log: Callable[[dict], None] = field(default=lambda _record: None, compare=False)


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
    length = _Length(len(first_line), extension or Extension(len(first_line)))
    maker = _LineMaker(engines, position, length, first_line[0].color, on_done, on_error)
    # When both sides play the best moves, KataGo's own sequence is kept as it is, and only made longer.
    kept = first_line if not engines.profile and not engines.my_profile else first_line[:1]
    maker.moves = kept[:-1]
    maker.add(kept[-1])


def build_line_from_start(
    engines: LineEngines,
    position: Position,
    on_done: Callable[[tuple[Move, ...]], None],
    on_error: Callable[[str], None],
    extension: Extension,
) -> None:
    """Make the sequence from the problem position itself, starting with the user's move (one query for each move).

    Args:
        engines: What the sequence is made with.
        position: The problem position. The user plays next_color.
        on_done: Called with the sequence (in KataGo's thread).
        on_error: Called with what went wrong (in KataGo's thread).
        extension: How long the sequence is made (it has at least one move).
    """
    maker = _LineMaker(engines, position, _Length(1, extension), position.next_color, on_done, on_error)
    maker.ask(position.next_color)


class _Length:
    """Tells when a sequence is complete: at KataGo's own length and at the aimed length (the longer one)."""

    def __init__(self, own: int, extension: Extension):
        """Keep the lengths."""
        self.own, self.extension = own, extension

    def complete(self, moves: int) -> bool:
        """True if a sequence of this many moves is complete."""
        return moves >= self.own and moves >= self.extension.length


class _LineMaker:
    """Adds the moves of a sequence one after another, each when KataGo has answered."""

    def __init__(self, engines: LineEngines, position: Position, length: _Length, my_color: str, on_done, on_error):
        """Keep what the sequence is made with (see build_line)."""
        self.engines, self.position, self.length, self.my_color = engines, position, length, my_color
        self.on_done, self.on_error = on_done, on_error
        self.moves: tuple[Move, ...] = ()
        self.after: list[Callable[[], None]] = []  # What waits for the end of the sequence (see defer).

    def defer(self, run: Callable[[], None]) -> None:
        """Run something when the sequence has ended, so that it does not slow down the moves of the sequence."""
        self.after.append(run)

    def add(self, move: Move) -> None:
        """Add a move, and ask for the next one unless the sequence is complete."""
        self.moves += (move,)
        if move.is_pass:
            self._finish("pass")
        elif self.length.complete(len(self.moves)):
            self._finish("length")
        else:
            self.ask(opponent(move.color))

    def _finish(self, reason: str) -> None:
        """Tell the end of the sequence and why it ended, hand over the sequence, and run what waited for the end."""
        self.engines.log(
            {
                "event": "human_line_end",
                "moves": len(self.moves),
                "own": self.length.own,
                "aimed": self.length.extension.length,
                "reason": reason,  # "length" (the aimed length), "pass", or "no_move" (KataGo had none).
            }
        )
        self.on_done(self.moves)
        for run in self.after:
            run()

    def ask(self, color: str) -> None:
        """Ask for the next move of a color: the user's (my_profile) or the opponent's (profile)."""
        mine = color == self.my_color
        profile = self.engines.my_profile if mine else self.engines.profile
        if not profile:
            self._ask_best(color)
        elif mine and self.engines.my_visits > 0:
            self._ask_human_best(color, profile)
        else:
            self._ask_human(color, profile)

    def _ask_best(self, color: str) -> None:
        """Ask for the best move of the sequence's model."""
        engines = self.engines
        query = position_query(self.position, self.moves, engines.visits, engines.wide_root_noise, engines.max_time)
        self.engines.best.query(query, self._receiver(lambda answer: self._best_move(answer, color)))

    def _ask_human(self, color: str, profile: str) -> None:
        """Ask for the move that a human of a profile would most likely play next."""
        query = human_query(self.position, self.moves, profile)
        self.engines.human.query(
            query, self._receiver(lambda answer: most_likely_move(answer, self.position.size, color))
        )

    def _ask_human_best(self, color: str, profile: str) -> None:
        """Ask for a natural and strong move that a human of a profile may play next (see LineEngines.my_visits)."""
        query = human_query(self.position, self.moves, profile)
        self.engines.human.query(query, self._policy_receiver(color))

    def _policy_receiver(self, color: str) -> Callable[[dict], None]:
        """Return the callback that takes the candidates from the human-like policy, and chooses among them."""
        engines = self.engines
        visits = engines.first_visits if engines.first_visits and not self.moves else engines.my_visits

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                candidates = candidate_moves(answer, self.position.size, color)
            except ValueError as error:
                self.on_error(str(error))
                return
            args = (engines.best, self.position, self.moves, candidates, visits, engines.max_time)
            choose_move(*args, engines.log, self.defer, self.add, self.on_error)

        return receive

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
                self._finish("no_move")
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
