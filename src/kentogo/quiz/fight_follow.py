"""The sequence of the AIs after a local fight, made until the place is settled (no Kivy here).

Both sides play the moves that a human of their rank would most likely play (see katago.human_moves), from the
position where the fight started, the user's side first. The sequence is made move by move, and ends when:

- the place is settled: every judged point belongs to one side by a wide margin (see quiz.fight_judge.is_settled),
  which means that stones were captured or live;
- a side plays away from the fight, or passes: the place needs no more moves;
- the sequence has FOLLOW_MOVES moves, or FOLLOW_SECONDS have passed since it was asked for.

The moves are told as they are made, so that the screen can show them while KataGo goes on. A side whose rank is
not known plays at the rank of the other side, and both play at DEFAULT_RANK when neither is known (see
follow_profiles).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from kentogo.common.types import Move, opponent
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import human_profile, human_query, most_likely_move
from kentogo.katago.queries import ownership_map, position_query, root_score, with_ownership
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_judge import fight_places, is_near, is_settled
from kentogo.quiz.human_line import PlayerRanks

DEFAULT_RANK = "9d"  # The rank of a side when no rank is known.
DEFAULT_PROFILE = human_profile(DEFAULT_RANK)
FOLLOW_MOVES = 60  # The sequence has at most this many moves.
FOLLOW_SECONDS = 60.0  # No move is added after this many seconds.

Point = tuple[int, int]


def follow_profiles(ranks: PlayerRanks) -> tuple[str, str]:
    """Return KataGo's humanSLProfiles of the user's side and of the opponent's side for the sequence of the AIs.

    A side whose rank is not known (or is not one of the human-like model's ranks) plays at the rank of the other
    side, and both play at DEFAULT_RANK when neither is known.
    """
    return _profile_of(ranks.mine, ranks.theirs), _profile_of(ranks.theirs, ranks.mine)


def _profile_of(*ranks: str) -> str:
    """Return the profile of the first rank that the human-like model has, else DEFAULT_PROFILE."""
    return next((profile for rank in ranks if (profile := human_profile(rank))), DEFAULT_PROFILE)


@dataclass(frozen=True)
class FollowPlan:
    """What the sequence is made with.

    Attributes:
        engine: KataGo, with the human-like model.
        fight: The fight; the sequence starts from its position, the user's side first.
        points: The judged points that the best play keeps (see quiz.fight_judge.kept_points). Without any, the
            place is never taken as settled.
        profiles: KataGo's humanSLProfiles of the user's side and of the opponent's side (see follow_profiles).
        visits: The visits of each reading of the areas.
        wide_root_noise: KaTrain's "wide_root_noise", or None for KataGo's own setting.
    """

    engine: AnalysisEngine
    fight: LocalFight
    points: list[Point]
    profiles: tuple[str, str]
    visits: int
    wide_root_noise: float | None


@dataclass(frozen=True)
class FollowLimits:
    """How long the sequence may be.

    Attributes:
        moves: The most moves.
        seconds: No move is added once this many seconds have passed since the start.
        clock: Returns the time in seconds (time.monotonic; tests give their own).
    """

    moves: int = FOLLOW_MOVES
    seconds: float = FOLLOW_SECONDS
    clock: Callable[[], float] = field(default=time.monotonic, compare=False)


def build_follow(
    plan: FollowPlan,
    on_move: Callable[[tuple[Move, ...]], None],
    on_done: Callable[[tuple[Move, ...]], None],
    on_error: Callable[[str], None],
    limits: FollowLimits | None = None,
) -> None:
    """Make the sequence move by move (the callbacks are called in KataGo's thread).

    Args:
        plan: What the sequence is made with.
        on_move: Called with the moves made so far, after each move.
        on_done: Called with the whole sequence when it is complete.
        on_error: Called with what went wrong (the moves told before are still valid).
        limits: How long the sequence may be (FollowLimits() when not given).
    """
    _FollowMaker(plan, limits or FollowLimits(), on_move, on_done, on_error).ask_move()


class _FollowMaker:
    """Adds the moves of the sequence one after another, each when KataGo has answered."""

    def __init__(self, plan: FollowPlan, limits: FollowLimits, on_move, on_done, on_error):
        """Keep what the sequence is made with, and start the time (see build_follow)."""
        self._plan, self._limits = plan, limits
        self._on_move, self._on_done, self._on_error = on_move, on_done, on_error
        self._deadline = limits.clock() + limits.seconds
        self._moves: tuple[Move, ...] = ()

    def ask_move(self) -> None:
        """Ask for the move that the side to play would most likely play."""
        position = self._plan.fight.position
        user_side = len(self._moves) % 2 == 0
        color = position.next_color if user_side else opponent(position.next_color)
        profile = self._plan.profiles[0 if user_side else 1]
        query = human_query(position, self._moves, profile)
        self._plan.engine.query(
            query, self._receiver(lambda answer: most_likely_move(answer, position.size, color), self._moved)
        )

    def _moved(self, move: Move) -> None:
        """Add a move, and go on unless the sequence is complete."""
        places = fight_places(self._plan.fight, self._moves)
        self._moves = (*self._moves, move)
        self._on_move(self._moves)
        if not is_near(move, places) or self._is_long():
            self._on_done(self._moves)
        else:
            self._ask_areas()

    def _is_long(self) -> bool:
        """True if the sequence has the most moves, or the time is up."""
        return len(self._moves) >= self._limits.moves or self._limits.clock() > self._deadline

    def _ask_areas(self) -> None:
        """Ask for the areas of the position after the moves, to see whether the place is settled."""
        plan = self._plan
        query = with_ownership(position_query(plan.fight.position, self._moves, plan.visits, plan.wide_root_noise))
        plan.engine.query(query, self._receiver(self._read_areas, self._judged))

    def _read_areas(self, answer: dict) -> dict[Point, float]:
        """Return the areas of KataGo's answer (raises ValueError if it is an error)."""
        root_score(answer)
        return ownership_map(answer, self._plan.fight.position.size)

    def _judged(self, areas: dict[Point, float]) -> None:
        """End the sequence if the place is settled, else ask for the next move."""
        if self._plan.points and is_settled(areas, self._plan.points):
            self._on_done(self._moves)
        else:
            self.ask_move()

    def _receiver(self, read: Callable[[dict], object], then: Callable) -> Callable[[dict], None]:
        """Return the callback that reads KataGo's final answer and passes what it read on (or tells the error)."""

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            try:
                value = read(answer)
            except ValueError as error:
                self._on_error(str(error))
                return
            then(value)

        return receive
