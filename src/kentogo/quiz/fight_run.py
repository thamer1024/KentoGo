"""Play a local fight problem against KataGo, move after move, until it is judged (the rules are in quiz.fight_judge).

start() reads the score of the fight's position. Then play() takes each move of the user: it checks that the move
is in the fight, asks KataGo for the position after it (with the areas, as many visits as the engine's max_visits),
and either judges the fight or lets the opponent answer:

- the strongest opponent (OPPONENT_STRONG) plays KataGo's best move of that same answer;
- the human-like opponent (OPPONENT_RANK) plays the move that a player of the opponent's rank would most likely
  play (one more query, with the human-like model; see katago.human_moves).

The callbacks are called in KataGo's thread (the screen moves them to its own). A move is played only after the
answer to the move before has come (the screen waits for it).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kentogo.common.types import Move, opponent
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import human_query, most_likely_move
from kentogo.katago.queries import best_sequence, ownership_map, position_query, root_score, with_ownership
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_judge import (
    OPPONENT_STRONG,
    OUTCOME_OPPONENT_LEFT,
    OUTCOME_USER_LEFT,
    FightOutcome,
    ended_outcome,
    fight_places,
    is_near,
    is_settled,
    judged_points,
    most_moves,
    score_loss,
)


@dataclass(frozen=True)
class FightPlay:
    """How KataGo plays the fight.

    Attributes:
        visits: The visits of each reading (the engine's max_visits).
        wide_root_noise: KaTrain's "wide_root_noise", or None for KataGo's own setting.
        opponent: OPPONENT_STRONG or OPPONENT_RANK (see quiz.fight_judge).
        profile: KataGo's human-like profile of the opponent's rank, such as "rank_15k" (used with OPPONENT_RANK;
            "" plays the strongest moves).
        tolerance: How many points the user's score may fall in a correct answer.
    """

    visits: int
    wide_root_noise: float | None
    opponent: str = OPPONENT_STRONG
    profile: str = ""
    tolerance: float = 3.0


class FightRun:
    """One local fight played against KataGo.

    Attributes:
        fight: The fight.
        played: The moves played from the fight's position, the user's first.
        start_lead: Black's score lead at the start, or None until start() has the answer.
        outcome: How the fight ended, or None while it goes on.
    """

    def __init__(self, engine: AnalysisEngine, fight: LocalFight, play: FightPlay):
        """Get ready to play a fight (nothing is asked yet)."""
        self.fight = fight
        self.played: tuple[Move, ...] = ()
        self.start_lead: float | None = None
        self.outcome: FightOutcome | None = None
        self._engine = engine
        self._play = play
        self._user_moves = 0

    @property
    def color(self) -> str:
        """Return the user's color."""
        return self.fight.position.next_color

    def start(self, on_ready: Callable[[], None], on_error: Callable[[str], None]) -> None:
        """Read the score of the fight's position, then call on_ready (or on_error with a message)."""

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                self.start_lead = root_score(answer)
            except ValueError as error:
                on_error(str(error))
                return
            on_ready()

        self._engine.query(self._query(()), receive)

    def play(
        self,
        move: Move,
        on_reply: Callable[[Move], None],
        on_end: Callable[[FightOutcome], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Play a move of the user: the opponent then answers (on_reply), or the fight ends (on_end).

        A move away from the fight (or a pass) ends it at once, before KataGo is asked.
        """
        if not is_near(move, fight_places(self.fight, self.played)):
            self._end(FightOutcome(OUTCOME_USER_LEFT), on_end)
            return
        self.played = (*self.played, move)
        self._user_moves += 1

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                self._after_user_move(answer, on_reply, on_end, on_error)
            except ValueError as error:
                on_error(str(error))

        self._engine.query(with_ownership(self._query(self.played)), receive)

    def _after_user_move(
        self,
        answer: dict,
        on_reply: Callable[[Move], None],
        on_end: Callable[[FightOutcome], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Judge the fight from KataGo's answer after the user's move, or let the opponent answer."""
        areas = ownership_map(answer, self.fight.position.size)
        loss = score_loss(self.start_lead, root_score(answer), self.color) if self.start_lead is not None else None
        if is_settled(areas, judged_points(self.fight)) or self._user_moves >= most_moves(self.fight):
            self._end(ended_outcome(areas, self.fight, loss, self._play.tolerance), on_end)
        elif self._play.opponent == OPPONENT_STRONG or not self._play.profile:
            self._strongest_reply(answer, loss, on_reply, on_end)
        else:
            self._human_reply(on_reply, on_error)

    def _strongest_reply(
        self, answer: dict, loss: float | None, on_reply: Callable[[Move], None], on_end: Callable[[FightOutcome], None]
    ) -> None:
        """Play KataGo's best move; when it leaves the fight (or passes), the user's move needed no answer."""
        points = best_sequence(answer)
        reply = Move.from_gtp(points[0], opponent(self.color)) if points else Move(opponent(self.color), None)
        if not is_near(reply, fight_places(self.fight, self.played)):
            self._end(FightOutcome(OUTCOME_OPPONENT_LEFT, loss), on_end)
            return
        self.played = (*self.played, reply)
        on_reply(reply)

    def _human_reply(self, on_reply: Callable[[Move], None], on_error: Callable[[str], None]) -> None:
        """Play the human-like move of the opponent's rank (it may leave the fight: the fight goes on)."""
        color = opponent(self.color)

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                reply = most_likely_move(answer, self.fight.position.size, color)
            except ValueError as error:
                on_error(str(error))
                return
            self.played = (*self.played, reply)
            on_reply(reply)

        self._engine.query(human_query(self.fight.position, self.played, self._play.profile), receive)

    def _end(self, outcome: FightOutcome, on_end: Callable[[FightOutcome], None]) -> None:
        """Keep the outcome and tell it."""
        self.outcome = outcome
        on_end(outcome)

    def _query(self, moves: tuple[Move, ...]) -> dict:
        """Return the query of the fight's position after some moves, with the play's visits."""
        return position_query(self.fight.position, moves, self._play.visits, self._play.wide_root_noise)
