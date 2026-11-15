"""The local fight problems of a sitting, asked one after another (the screen only shows what this module says).

Each fight is played against KataGo (see quiz.fight_run): the user plays a move, KataGo answers, and so on,
until the fight is judged. The fight goes through these phases:

- PHASE_STARTING: KataGo reads the score of the fight's position;
- PHASE_TURN: the user's turn (a click on the board is a move);
- PHASE_WAITING: KataGo reads the position after the user's move, and answers or judges the fight;
- PHASE_ENDED: the fight was judged (and its answer was saved); its sequences can be shown (see quiz.fight_lines),
  and KataGo makes the sequence of the AIs;
- PHASE_ERROR: KataGo could not answer (the fight is not saved; the next fight can be asked).

The answers of KataGo come in its own thread: they are moved to the screen's thread (in_main) before anything
is changed, and the answers about a fight that is no longer asked are not used.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from kentogo.common.board import Board, IllegalMoveError
from kentogo.common.types import Move
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_judge import FightOutcome
from kentogo.quiz.fight_lines import FightLines
from kentogo.quiz.fight_run import FightRun

PHASE_STARTING = "starting"
PHASE_TURN = "turn"
PHASE_WAITING = "waiting"
PHASE_ENDED = "ended"
PHASE_ERROR = "error"


class FightListener(Protocol):
    """What the screen is told (always in its own thread)."""

    def changed(self) -> None:
        """The fight asked now, its moves or its phase changed (or the fights have all been asked)."""


class FightQuiz:
    """The local fights of a sitting.

    Attributes:
        fights: The fights to ask, in order.
        index: The number of the fight asked now, from 0 (len(fights) after the last one).
        run: The fight asked now, or None after the last one.
        phase: The phase of the fight asked now (see the module's docstring).
        error: What KataGo said when it could not answer ("" without an error).
        lines: The sequences of the fight asked now, after it has ended (None before).
    """

    def __init__(
        self,
        fights: list[LocalFight],
        make_run: Callable[[LocalFight], FightRun],
        save: Callable[[FightRun], None],
        listener: FightListener,
        in_main: Callable[[Callable], Callable],
    ):
        """Get ready to ask the fights (start() asks the first one).

        Args:
            fights: The fights to ask, in order.
            make_run: Makes the play of a fight against KataGo.
            save: Saves the answer of a fight that has ended (called once for each fight).
            listener: Told about every change.
            in_main: Turns a function into one that runs in the screen's thread.
        """
        self.fights = fights
        self.index = 0
        self.run: FightRun | None = None
        self.phase = PHASE_STARTING
        self.error = ""
        self.lines: FightLines | None = None
        self._make_run = make_run
        self._save = save
        self._listener = listener
        self._in_main = in_main
        self._left = False

    def start(self, index: int) -> None:
        """Ask the fight with this number (after the last one: no fight is asked)."""
        self.index = index
        self.error = ""
        self.lines = None
        if index >= len(self.fights):
            self.run = None
            self._listener.changed()
            return
        run = self._make_run(self.fights[index])
        self.run = run
        self.phase = PHASE_STARTING
        self._listener.changed()
        run.start(self._for(run, self._ready), self._for(run, self._failed))

    def next_fight(self) -> None:
        """Ask the next fight (the fight asked now is left as it is, also while KataGo is reading)."""
        if self.run is not None:
            self.start(self.index + 1)

    def play(self, point: tuple[int, int]) -> str:
        """Take a point of the board as the user's move, in the user's turn.

        Returns:
            "" when the move was taken (or it is not the user's turn), or why the move is not allowed.
        """
        run = self.run
        if run is None or self.phase != PHASE_TURN:
            return ""
        move = Move(run.color, point)
        try:
            board_after(run).play(move)
        except IllegalMoveError as error:
            return str(error)
        self.phase = PHASE_WAITING
        self._listener.changed()
        run.play(move, self._for(run, self._replied), self._for(run, self._ended), self._for(run, self._failed))
        return ""

    def leave(self) -> None:
        """Stop using KataGo's answers (the screen is closed)."""
        self._left = True

    def _for(self, run: FightRun, action: Callable) -> Callable:
        """Return a callback that runs action in the screen's thread, only while run is the fight asked now."""

        def callback(*values) -> None:
            if not self._left and run is self.run:
                action(*values)

        return self._in_main(callback)

    def _ready(self) -> None:
        """KataGo has read the fight's position: the user plays."""
        self.phase = PHASE_TURN
        self._listener.changed()

    def _replied(self, _reply: Move) -> None:
        """The opponent answered: the user plays again."""
        self.phase = PHASE_TURN
        self._listener.changed()

    def _ended(self, _outcome: FightOutcome) -> None:
        """The fight was judged: save it, and let KataGo make the sequence of the AIs."""
        run = self.run
        self.phase = PHASE_ENDED
        self.lines = FightLines(run.played, run.fight.game_line)
        self._save(run)
        self._listener.changed()
        run.ask_ai_line(self._for(run, self._ai_line_came), self._for(run, self._ai_line_failed))

    def _ai_line_came(self, line: tuple[Move, ...]) -> None:
        """Keep the sequence of the AIs."""
        self.lines.set_ai_line(line)
        self._listener.changed()

    def _ai_line_failed(self, _message: str) -> None:
        """Tell that the sequence of the AIs could not be made (the fight's answer is kept)."""
        self.lines.ai_failed()
        self._listener.changed()

    def _failed(self, message: str) -> None:
        """KataGo could not answer."""
        self.phase = PHASE_ERROR
        self.error = message
        self._listener.changed()


def board_after(run: FightRun) -> Board:
    """Return the board of a fight's position after the moves played so far."""
    board = Board.from_position(run.fight.position)
    for move in run.played:
        board.play(move)
    return board
