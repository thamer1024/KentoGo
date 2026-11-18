"""Play a local fight problem against KataGo, move after move, until it is judged (the rules are in quiz.fight_judge).

start() reads the score and the areas of the fight's position. Then play() takes each move of the user: it checks that the move
is in the fight, asks KataGo for the position after it (with the areas, as many visits as the engine's max_visits),
and either judges the fight or lets the opponent answer:

- the strongest opponent (OPPONENT_STRONG) plays KataGo's best move of that same answer;
- the human-like opponent (OPPONENT_RANK) plays the move that a player of the opponent's rank would most likely
  play (one more query, with the human-like model; see katago.human_moves).

KataGo's areas settle before a group in a ladder is really captured, and the fight would be judged at the first atari
without playing the ladder. So while a group is being chased (see quiz.fight_stones), the fight is not judged: the
opponent answers among the moves around the group, as it plays otherwise (KataGo's best, or the human-like move), until
the group is captured or the chase is broken (at most LADDER_USER_MOVES moves of the user).

After the fight, ask_ai_line() makes the sequence in which both sides play the human-like moves of their ranks, from
the fight's position until the place is settled (see quiz.fight_follow); ask_strong_line() makes it with KataGo's
best moves for both sides.

The callbacks are called in KataGo's thread (the screen moves them to its own). A move is played only after the
answer to the move before has come (the screen waits for it).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from kentogo.common.types import Move, opponent
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import human_query, most_likely_among, most_likely_move
from kentogo.katago.queries import (
    best_sequence,
    ownership_map,
    position_query,
    root_score,
    with_allowed_moves,
    with_ownership,
)
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_follow import DEFAULT_PROFILE, FollowEnd, FollowPlan, build_follow, build_strong_follow
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
from kentogo.quiz.fight_stones import ChaseTracker

LADDER_USER_MOVES = 40  # While a ladder goes on, the user may play this many moves.


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
        line_my_profile: KataGo's human-like profile of the user's side of the sequence of the AIs after the fight
            (see quiz.fight_follow.follow_profiles).
        line_profile: The same for the opponent's side.
        log_line: Told a record about how the sequence of the AIs ended (see line_log.log_line).
    """

    visits: int
    wide_root_noise: float | None
    opponent: str = OPPONENT_STRONG
    profile: str = ""
    tolerance: float = 3.0
    line_my_profile: str = DEFAULT_PROFILE
    line_profile: str = DEFAULT_PROFILE
    log_line: Callable[[dict], None] = field(default=lambda _record: None, compare=False)


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
        self._chase = ChaseTracker(fight.position)

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

        When KataGo's best reply is away from the fight, the place needs no more moves (see quiz.fight_judge). While a
        group is being chased, the fight goes on: the opponent answers among the moves around it (see
        quiz.fight_stones).
        """
        areas = ownership_map(answer, self.fight.position.size)
        lead = root_score(answer)
        before, self._last_lead = self._last_lead, lead
        loss = score_loss(self.start_lead, lead, self.color) if self.start_lead is not None else None
        self._chase.update(self.played, areas)
        moves = self._chase.local_moves(self.played, opponent(self.color))
        if moves and self._user_moves < LADDER_USER_MOVES:
            self._chase_reply(moves, on_reply, on_error)
            return
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

    def _chase_reply(self, moves: list[str], on_reply: Callable[[Move], None], on_error: Callable[[str], None]) -> None:
        """Let the opponent answer among the moves around the chased group, as it plays (strongest or human-like)."""
        color = opponent(self.color)
        size = self.fight.position.size
        human = self._play.opponent != OPPONENT_STRONG and bool(self._play.profile)
        if human:
            query = human_query(self.fight.position, self.played, self._play.profile)
        else:
            query = with_allowed_moves(self._query(self.played), color, moves)

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                reply = most_likely_among(answer, size, color, moves) if human else self._best_of(answer, color)
            except ValueError as error:
                on_error(str(error))
                return
            self.played = (*self.played, reply)
            on_reply(reply)

        self._engine.query(query, receive)

    @staticmethod
    def _best_of(answer: dict, color: str) -> Move:
        """Return KataGo's best move of an answer (raises ValueError if the answer is an error)."""
        root_score(answer)
        points = best_sequence(answer)
        return Move.from_gtp(points[0], color) if points else Move(color, None)

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

    def ask_ai_line(
        self,
        on_move: Callable[[tuple[Move, ...]], None],
        on_done: Callable[[tuple[Move, ...], FollowEnd], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Make the sequence of the AIs from the fight's position, until the place is settled (see quiz.fight_follow).

        Both sides play the human-like moves of their ranks (FightPlay.line_my_profile and line_profile). on_move
        gets the moves made so far after each move, and on_done the whole sequence and why it ended.
        """
        build_follow(self._follow_plan(), on_move, on_done, on_error)

    def ask_strong_line(
        self,
        on_move: Callable[[tuple[Move, ...]], None],
        on_done: Callable[[tuple[Move, ...], FollowEnd], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Make the sequence of the strongest AI from the fight's position (see quiz.fight_follow.build_strong_follow).

        Both sides play KataGo's best moves. The callbacks are those of ask_ai_line.
        """
        build_strong_follow(self._follow_plan(), on_move, on_done, on_error)

    def _follow_plan(self) -> FollowPlan:
        """Return what the sequences of the AIs are made with."""
        play = self._play
        profiles = (play.line_my_profile, play.line_profile)
        return FollowPlan(
            self._engine, self.fight, self.points, profiles, play.visits, play.wide_root_noise, play.log_line
        )

    def _end(self, outcome: FightOutcome, on_end: Callable[[FightOutcome], None]) -> None:
        """Keep the outcome and tell it."""
        self.outcome = outcome
        on_end(outcome)

    def _query(self, moves: tuple[Move, ...]) -> dict:
        """Return the query of the fight's position after some moves, with the play's visits."""
        return position_query(self.fight.position, moves, self._play.visits, self._play.wide_root_noise)
