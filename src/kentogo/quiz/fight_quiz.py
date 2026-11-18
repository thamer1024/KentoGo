"""The local fight problems of a sitting, asked one after another (the screen only shows what this module says).

Each fight is played against KataGo (see quiz.fight_run): the user plays a move, KataGo answers, and so on,
until the fight is judged. The fight goes through these phases:

- PHASE_STARTING: KataGo reads the score of the fight's position;
- PHASE_TURN: the user's turn (a click on the board is a move);
- PHASE_WAITING: KataGo reads the position after the user's move, and answers or judges the fight;
- PHASE_ENDED: the fight was judged (and its answer was saved); its sequences can be shown and stepped through
  (see quiz.fight_lines), and follow() has KataGo make the sequence of the AIs from the fight's position (no stone
  can be put on the board any more);
- PHASE_ERROR: KataGo could not answer (the fight is not saved; the next fight can be asked).

The answers of KataGo come in its own thread: they are moved to the screen's thread (in_main) before anything
is changed, and the answers about a fight that is no longer asked are not used.

Each fight is shown turned as choose_transform says. Only what the user sees and clicks is turned: the fight, its
moves and its sequences stay in the original coordinates, for KataGo and for the saved answer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from kentogo.common.board import Board, IllegalMoveError
from kentogo.common.types import Move, Position
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_follow import FollowEnd, is_inconclusive
from kentogo.quiz.fight_judge import FightOutcome
from kentogo.quiz.fight_lines import AI_CALCULATING, LINE_AI, LINE_STRONG, FightLines
from kentogo.quiz.fight_run import FightRun
from kentogo.quiz.transform import IDENTITY, BoardTransform

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
        transform: How the fight asked now is turned on the screen.
    """

    def __init__(
        self,
        fights: list[LocalFight],
        make_run: Callable[[LocalFight], FightRun],
        save: Callable[[FightRun], None],
        listener: FightListener,
        in_main: Callable[[Callable], Callable],
        choose_transform: Callable[[], BoardTransform] = lambda: IDENTITY,
    ):
        """Get ready to ask the fights (start() asks the first one).

        Args:
            fights: The fights to ask, in order.
            make_run: Makes the play of a fight against KataGo.
            save: Saves the answer of a fight that has ended (called once for each fight).
            listener: Told about every change.
            in_main: Turns a function into one that runs in the screen's thread.
            choose_transform: Returns how to turn each fight on the screen.
        """
        self.fights = fights
        self.index = 0
        self.run: FightRun | None = None
        self.phase = PHASE_STARTING
        self.error = ""
        self.lines: FightLines | None = None
        self.transform = IDENTITY
        self._make_run = make_run
        self._save = save
        self._listener = listener
        self._in_main = in_main
        self._choose_transform = choose_transform
        self._left = False
        self._ai_asked = False

    def start(self, index: int) -> None:
        """Ask the fight with this number (after the last one: no fight is asked)."""
        self.index = index
        self.error = ""
        self.lines = None
        self._ai_asked = False
        if index >= len(self.fights):
            self.run = None
            self._listener.changed()
            return
        run = self._make_run(self.fights[index])
        self.run = run
        self.transform = self._choose_transform()
        self.phase = PHASE_STARTING
        self._listener.changed()
        run.start(self._for(run, self._ready), self._for(run, self._failed))

    def next_fight(self) -> None:
        """Ask the next fight (the fight asked now is left as it is, also while KataGo is reading)."""
        if self.run is not None:
            self.start(self.index + 1)

    def play(self, point: tuple[int, int]) -> str:
        """Take a point of the board shown as the user's move, in the user's turn.

        Returns:
            "" when the move was taken (or it is not the user's turn), or why the move is not allowed (with the
            point as it is shown).
        """
        run = self.run
        if run is None or self.phase != PHASE_TURN:
            return ""
        shown_move = Move(run.color, point)
        try:
            self._shown_board().play(shown_move)
        except IllegalMoveError as error:
            return str(error)
        move = self.transform.inverse().move(shown_move, run.fight.position.size)
        self.phase = PHASE_WAITING
        self._listener.changed()
        run.play(move, self._for(run, self._replied), self._for(run, self._ended), self._for(run, self._failed))
        return ""

    def follow(self) -> None:
        """Show the sequence of the AIs from the fight's position (only after the fight has ended).

        KataGo makes it at the first call, move by move: the moves made so far are shown meanwhile. Once the strongest
        AI has played it again (see _ask_strong_line), each call shows the other of the two sequences of the AIs.
        """
        run, lines = self.run, self.lines
        if run is None or lines is None:
            return
        if lines.name == LINE_AI and lines.strong_asked:
            lines.show_strong_line()
        elif lines.name != LINE_AI:
            lines.show_ai_line()
        if not self._ai_asked:
            self._ai_asked = True
            run.ask_ai_line(
                self._for(run, self._follow_moved),
                self._for(run, self._follow_done),
                self._for(run, self._follow_failed),
            )
        self._listener.changed()

    @property
    def calculating_line(self) -> str | None:
        """Return the sequence that KataGo is making now (LINE_AI or LINE_STRONG), or None."""
        lines = self.lines
        if lines is None:
            return None
        if lines.strong_asked and lines.strong_state == AI_CALCULATING:
            return LINE_STRONG
        return LINE_AI if self._ai_asked and lines.ai_state == AI_CALCULATING else None

    def step_forward(self) -> None:
        """Show one move more of the sequence shown (only after the fight has ended)."""
        if self.lines is not None:
            self.lines.forward()
            self._listener.changed()

    def step_back(self) -> None:
        """Show one move less of the sequence shown (only after the fight has ended)."""
        if self.lines is not None:
            self.lines.back()
            self._listener.changed()

    def shown_position(self) -> Position:
        """Return the position of the fight asked now, as it is shown."""
        return self.transform.position(self.run.fight.position)

    def shown_moves(self) -> tuple[Move, ...]:
        """Return the moves to show, turned: the sequence chosen after the fight has ended, else those played."""
        moves = self.lines.shown() if self.lines is not None else self.run.played
        return self.transform.moves(moves, self.run.fight.position.size)

    def leave(self) -> None:
        """Stop using KataGo's answers (the screen is closed)."""
        self._left = True

    def _shown_board(self) -> Board:
        """Return the board as it is shown, after the moves played so far."""
        board = Board.from_position(self.shown_position())
        for move in self.transform.moves(self.run.played, self.run.fight.position.size):
            board.play(move)
        return board

    def _for(self, run: FightRun, action: Callable) -> Callable:
        """Return a callback that runs action in the screen's thread, only while run is the fight asked now."""

        def callback(*values) -> None:
            if not self._left and run is self.run:
                action(*values)

        return self._in_main(callback)

    def _ready(self) -> None:
        """KataGo has read the fight's position: the user plays (a fight with no point to judge is not asked)."""
        if not self.run.points:
            self.next_fight()
            return
        self.phase = PHASE_TURN
        self._listener.changed()

    def _replied(self, _reply: Move) -> None:
        """The opponent answered: the user plays again."""
        self.phase = PHASE_TURN
        self._listener.changed()

    def _ended(self, _outcome: FightOutcome) -> None:
        """The fight was judged: save it, and keep its sequences to be shown."""
        run = self.run
        self.phase = PHASE_ENDED
        self.lines = FightLines(run.played, run.fight.game_line)
        self._save(run)
        self._listener.changed()

    def _follow_moved(self, line: tuple[Move, ...]) -> None:
        """Show the moves of the sequence of the AIs made so far."""
        self.lines.update_ai_line(line)
        self._listener.changed()

    def _follow_done(self, line: tuple[Move, ...], end: FollowEnd) -> None:
        """Keep the whole sequence of the AIs and why it ended; if it did not conclude, the strongest AI plays again."""
        self.lines.set_ai_line(line, end)
        if is_inconclusive(end):
            self._ask_strong_line()
        self._listener.changed()

    def _follow_failed(self, _message: str) -> None:
        """Tell that the sequence of the AIs could not be made (the fight's answer is kept); try the strongest AI."""
        self.lines.ai_failed()
        self._ask_strong_line()
        self._listener.changed()

    def _ask_strong_line(self) -> None:
        """Show the sequence of the strongest AI from its first move, and have KataGo make it (once)."""
        run, lines = self.run, self.lines
        if lines.strong_asked:
            return
        lines.start_strong_line()
        run.ask_strong_line(
            self._for(run, self._strong_moved), self._for(run, self._strong_done), self._for(run, self._strong_failed)
        )

    def _strong_moved(self, line: tuple[Move, ...]) -> None:
        """Show the moves of the sequence of the strongest AI made so far."""
        self.lines.update_strong_line(line)
        self._listener.changed()

    def _strong_done(self, line: tuple[Move, ...], end: FollowEnd) -> None:
        """Keep the whole sequence of the strongest AI and why it ended."""
        self.lines.set_strong_line(line, end)
        self._listener.changed()

    def _strong_failed(self, _message: str) -> None:
        """Tell that the sequence of the strongest AI could not be made."""
        self.lines.strong_failed()
        self._listener.changed()

    def _failed(self, message: str) -> None:
        """KataGo could not answer."""
        self.phase = PHASE_ERROR
        self.error = message
        self._listener.changed()
