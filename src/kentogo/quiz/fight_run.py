"""Play a local fight problem against KataGo, move after move, until it is judged (the rules are in quiz.fight_judge).

start() reads the score and the areas of the fight's position. Then play() takes each move of the user: it checks that the move
is in the fight, asks KataGo for the position after it (with the areas, as many visits as the engine's max_visits),
and either judges the fight or lets the opponent answer:

- the strongest opponent (OPPONENT_STRONG) plays KataGo's best move of that same answer;
- the human-like opponent (OPPONENT_RANK) plays the move that a player of the opponent's rank would most likely
  play (one more query, with the human-like model; see katago.human_moves).

After the fight, ask_ai_line() makes the sequence in which both sides play as the opponent was set to play: both
KataGo's best moves (OPPONENT_STRONG), or both the human-like moves of their ranks (OPPONENT_RANK), as long as
the game's sequence of the fight (see quiz.human_line).

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
    NEEDLESS_LOSS,
    OPPONENT_STRONG,
    OUTCOME_OPPONENT_LEFT,
    OUTCOME_USER_LEFT,
    FightOutcome,
    ended_outcome,
    fight_places,
    is_near,
    is_settled,
    judged_points,
    kept_points,
    most_moves,
    score_loss,
)
from kentogo.quiz.human_line import Extension, LineEngines, build_line

AI_LINE_SECONDS = 60.0  # No move is added to the sequence of the AIs after this many seconds.


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
        my_profile: KataGo's human-like profile of the user's rank, for the user's side of the sequence of the
            AIs after the fight (used with OPPONENT_RANK; "" plays the strongest moves).
    """

    visits: int
    wide_root_noise: float | None
    opponent: str = OPPONENT_STRONG
    profile: str = ""
    tolerance: float = 3.0
    my_profile: str = ""


class FightRun:
    """One local fight played against KataGo.

    Attributes:
        fight: The fight.
        played: The moves played from the fight's position, the user's first (with the user's last move, even
            when it left the fight).
        start_lead: Black's score lead at the start, or None until start() has the answer.
        points: The judged points that the best play keeps (see quiz.fight_judge.kept_points), known after start().
        outcome: How the fight ended, or None while it goes on.
    """

    def __init__(self, engine: AnalysisEngine, fight: LocalFight, play: FightPlay):
        """Get ready to play a fight (nothing is asked yet)."""
        self.fight = fight
        self.played: tuple[Move, ...] = ()
        self.start_lead: float | None = None
        self.points: list[tuple[int, int]] = []
        self.outcome: FightOutcome | None = None
        self._engine = engine
        self._play = play
        self._user_moves = 0
        self._last_lead: float | None = None  # Black's lead before the user's move.

    @property
    def color(self) -> str:
        """Return the user's color."""
        return self.fight.position.next_color

    def start(self, on_ready: Callable[[], None], on_error: Callable[[str], None]) -> None:
        """Read the score and the areas of the fight's position, then call on_ready (or on_error with a message)."""

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                self.start_lead = root_score(answer)
                areas = ownership_map(answer, self.fight.position.size)
            except ValueError as error:
                on_error(str(error))
                return
            self._last_lead = self.start_lead
            self.points = kept_points(judged_points(self.fight), areas, self.color)
            on_ready()

        self._engine.query(with_ownership(self._query(())), receive)

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
        places = fight_places(self.fight, self.played)
        self.played = (*self.played, move)
        if not is_near(move, places):
            self._end(FightOutcome(OUTCOME_USER_LEFT), on_end)
            return
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
        """Judge the fight from KataGo's answer after the user's move, or let the opponent answer.

        When KataGo's best reply is away from the fight, the place needs no more moves (see quiz.fight_judge).
        """
        areas = ownership_map(answer, self.fight.position.size)
        lead = root_score(answer)
        before, self._last_lead = self._last_lead, lead
        loss = score_loss(self.start_lead, lead, self.color) if self.start_lead is not None else None
        best = self._best_reply(answer)
        if is_settled(areas, self.points) or self._user_moves >= most_moves(self.fight):
            self._end(self._ended(areas, loss), on_end)
        elif not is_near(best, fight_places(self.fight, self.played)):
            move_loss = score_loss(before, lead, self.color) if before is not None else 0.0
            needless = move_loss > NEEDLESS_LOSS
            self._end(FightOutcome(OUTCOME_OPPONENT_LEFT, loss) if needless else self._ended(areas, loss), on_end)
        elif self._play.opponent == OPPONENT_STRONG or not self._play.profile:
            self.played = (*self.played, best)
            on_reply(best)
        else:
            self._human_reply(on_reply, on_error)

    def _best_reply(self, answer: dict) -> Move:
        """Return KataGo's best reply to the user's move (a pass when it has none)."""
        points = best_sequence(answer)
        return Move.from_gtp(points[0], opponent(self.color)) if points else Move(opponent(self.color), None)

    def _ended(self, areas: dict, loss: float | None) -> FightOutcome:
        """Return the outcome of the fight judged now."""
        return ended_outcome(areas, self.points, self.color, loss, self._play.tolerance)

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

    def ask_ai_line(self, on_done: Callable[[tuple[Move, ...]], None], on_error: Callable[[str], None]) -> None:
        """Make the sequence of the AIs from the fight's position, as long as the game's sequence of the fight.

        Both sides play as the opponent was set to play (see the module's docstring); on_done gets the sequence.
        """
        play = self._play
        rank = play.opponent != OPPONENT_STRONG
        profile, my_profile = (play.profile, play.my_profile) if rank else ("", "")
        engines = LineEngines(self._engine, self._engine, play.visits, play.wide_root_noise, profile, my_profile)
        extension = Extension(max(len(self.fight.game_line), 1), AI_LINE_SECONDS)
        position = self.fight.position

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                first = self._first_ai_move(answer, my_profile)
            except ValueError as error:
                on_error(str(error))
                return
            build_line(engines, position, (first,), on_done, on_error, extension)

        query = human_query(position, (), my_profile) if my_profile else self._query(())
        self._engine.query(query, receive)

    def _first_ai_move(self, answer: dict, my_profile: str) -> Move:
        """Return the user's side's first move of the sequence of the AIs, from KataGo's answer.

        Raises:
            ValueError: If the answer is an error, or has no move.
        """
        if my_profile:
            return most_likely_move(answer, self.fight.position.size, self.color)
        root_score(answer)  # Raises on an error.
        points = best_sequence(answer)
        if not points:
            raise ValueError("KataGo's answer has no move")
        return Move.from_gtp(points[0], self.color)

    def _end(self, outcome: FightOutcome, on_end: Callable[[FightOutcome], None]) -> None:
        """Keep the outcome and tell it."""
        self.outcome = outcome
        on_end(outcome)

    def _query(self, moves: tuple[Move, ...]) -> dict:
        """Return the query of the fight's position after some moves, with the play's visits."""
        return position_query(self.fight.position, moves, self._play.visits, self._play.wide_root_noise)
