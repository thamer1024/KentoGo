"""The sequence of the AIs after a local fight, made until the place is settled (no Kivy here).

Both sides play the moves that a human of their rank would most likely play (see katago.human_moves), from the
position where the fight started, the user's side first. The sequence is made move by move, and ends when:

- the place is settled: every judged point belongs to one side by a wide margin (see quiz.fight_judge.is_settled),
  which means that stones were captured or live;
- a side plays away from the fight, or passes: the place needs no more moves;
- the sequence has FOLLOW_MOVES moves, or FOLLOW_SECONDS have passed since it was asked for.

Why it ended is told with the sequence (FollowEnd), and logged (see FollowPlan.log).

build_strong_follow makes the same sequence with KataGo's best moves for both sides (the human-like model is not
asked), for when the human-like sequence did not conclude how the place ended (see is_inconclusive).

In both sequences, while a group is being chased (see quiz.fight_stones), both sides choose among the moves around
it, and the sequence goes on until the group is captured or the chase is broken, even if the place is settled.

The moves are told as they are made, so that the screen can show them while KataGo goes on. A side whose rank is
not known plays at the rank of the other side, and both play at DEFAULT_RANK when neither is known (see
follow_profiles).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from kentogo.common.board import Board
from kentogo.common.types import Move, opponent
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import human_profile, human_query, most_likely_among, most_likely_move
from kentogo.katago.queries import (
    best_sequence,
    ownership_map,
    position_query,
    root_score,
    with_allowed_moves,
    with_ownership,
)
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_judge import fight_places, is_near, is_settled
from kentogo.quiz.fight_stones import ChaseTracker
from kentogo.quiz.human_line import PlayerRanks

DEFAULT_RANK = "9d"  # The rank of a side when no rank is known.
DEFAULT_PROFILE = human_profile(DEFAULT_RANK)
FOLLOW_MOVES = 30  # The sequence has at most this many moves.
FOLLOW_SECONDS = 60.0  # No move is added after this many seconds.
STRONG_MOVES = 50  # The sequence of the strongest AI has at most this many moves (a ladder can be long).
STRONG_SECONDS = 90.0  # No move of it is added after this many seconds.

END_LIVED = "lived"  # The judged stones live (color: the color that lives).
END_KILLED = "killed"  # The judged stones are captured (color: the color that captures).
END_TERRITORY = "territory"  # The judged empty points belong to one side (color: that side).
END_LIVED_KILLED = "lived_killed"  # One side's judged stones live and the other's are captured (color: that side).
END_ALL = "all"  # All the judged points belong to one side, in other ways than above (color: that side).
END_MIXED = "mixed"  # The judged points belong to both sides (black and white: the points each owns).
END_LEFT = "left"  # A side played away from the fight.
END_PASS = "pass"  # A side passed.
END_LENGTH = "length"  # The sequence has FOLLOW_MOVES moves.
END_TIME = "time"  # FOLLOW_SECONDS have passed.
INCONCLUSIVE = (END_MIXED, END_LENGTH, END_TIME)  # The ends that do not tell how the place ended.

Point = tuple[int, int]


@dataclass(frozen=True)
class FollowEnd:
    """Why the sequence ended.

    Attributes:
        reason: One of the END_* values.
        color: "B" or "W" for END_LIVED, END_KILLED, END_TERRITORY, END_LIVED_KILLED and END_ALL, else None.
        black: For END_MIXED, how many judged points belong to black.
        white: For END_MIXED, how many judged points belong to white.
    """

    reason: str
    color: str | None = None
    black: int = 0
    white: int = 0


def is_inconclusive(end: FollowEnd) -> bool:
    """True if the sequence of the AIs did not conclude how the place ended."""
    return end.reason in INCONCLUSIVE


def settled_end(fight: LocalFight, areas: dict[Point, float], points: list[Point]) -> FollowEnd:
    """Return how a settled place ended.

    Each point is judged by its stone at the start of the fight (if any) against the color that owns it now: lived,
    killed or territory. When all the points agree, that is the end. When one side owns all of them, it is
    END_LIVED_KILLED (its stones live and the other's are captured) or END_ALL. When both sides own some, END_MIXED.
    """
    board = Board.from_position(fight.position)
    ends = [_point_end(board.stone_at(point), areas.get(point, 0.0)) for point in points]
    if len(set(ends)) == 1:
        return FollowEnd(*ends[0])
    colors = {color for _reason, color in ends}
    if len(colors) == 1:
        return _one_side_end(colors.pop(), {reason for reason, _color in ends})
    black = sum(color == "B" for _reason, color in ends)
    return FollowEnd(END_MIXED, None, black, len(ends) - black)


def _one_side_end(color: str, reasons: set[str]) -> FollowEnd:
    """Return the end of a place whose judged points all belong to color, though they did not end in one way."""
    return FollowEnd(END_LIVED_KILLED if reasons == {END_LIVED, END_KILLED} else END_ALL, color)


def _point_end(stone: str | None, area: float) -> tuple[str, str]:
    """Return (END_*, color) of one judged point: its first stone against the color that owns it at the end."""
    owner = "B" if area > 0 else "W"
    if stone is None:
        return END_TERRITORY, owner
    return (END_LIVED if stone == owner else END_KILLED), owner


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
        log: Told a record (see line_log) when the sequence ends or fails.
    """

    engine: AnalysisEngine
    fight: LocalFight
    points: list[Point]
    profiles: tuple[str, str]
    visits: int
    wide_root_noise: float | None
    log: Callable[[dict], None] = field(default=lambda _record: None, compare=False)


@dataclass(frozen=True)
class FollowLimits:
    """How long the sequence may be.

    Attributes:
        moves: The most moves.
        seconds: No move is added once this many seconds have passed since the start.
        clock: Returns the time in seconds (time.monotonic; tests give their own).
        chase_moves: The most moves while a group is being chased.
        chase_seconds: The seconds since the start after which no move is added while a group is being chased.
    """

    moves: int = FOLLOW_MOVES
    seconds: float = FOLLOW_SECONDS
    clock: Callable[[], float] = field(default=time.monotonic, compare=False)
    chase_moves: int = STRONG_MOVES
    chase_seconds: float = STRONG_SECONDS


def build_follow(
    plan: FollowPlan,
    on_move: Callable[[tuple[Move, ...]], None],
    on_done: Callable[[tuple[Move, ...], FollowEnd], None],
    on_error: Callable[[str], None],
    limits: FollowLimits | None = None,
) -> None:
    """Make the sequence move by move (the callbacks are called in KataGo's thread).

    Args:
        plan: What the sequence is made with.
        on_move: Called with the moves made so far, after each move.
        on_done: Called with the whole sequence and why it ended, when it is complete.
        on_error: Called with what went wrong (the moves told before are still valid).
        limits: How long the sequence may be (FollowLimits() when not given).
    """
    _FollowMaker(plan, limits or FollowLimits(), on_move, on_done, on_error).ask_move()


def build_strong_follow(
    plan: FollowPlan,
    on_move: Callable[[tuple[Move, ...]], None],
    on_done: Callable[[tuple[Move, ...], FollowEnd], None],
    on_error: Callable[[str], None],
    limits: FollowLimits | None = None,
) -> None:
    """Make the sequence of the strongest AI move by move: both sides play KataGo's best moves.

    It starts from the same position and ends in the same ways as build_follow, with the same callbacks.
    plan.profiles is not used (the human-like model is not asked).
    """
    limits = limits or FollowLimits(STRONG_MOVES, STRONG_SECONDS)
    _StrongFollowMaker(plan, limits, on_move, on_done, on_error).ask_move()


class _FollowMaker:
    """Adds the moves of the sequence one after another, each when KataGo has answered."""

    _LOG_LINE = "ai_follow"  # The "line" of the log records (their events are told "<line>_end" and "<line>_error").

    def __init__(self, plan: FollowPlan, limits: FollowLimits, on_move, on_done, on_error):
        """Keep what the sequence is made with, and start the time (see build_follow)."""
        self._plan, self._limits = plan, limits
        self._on_move, self._on_done, self._on_error = on_move, on_done, on_error
        self._started = limits.clock()
        self._moves: tuple[Move, ...] = ()
        self._chase = ChaseTracker(plan.fight.position)

    def ask_move(self) -> None:
        """Ask for the move that the side to play would most likely play (around the group, during a chase)."""
        position = self._plan.fight.position
        color = self._next_color()
        profile = self._plan.profiles[0 if len(self._moves) % 2 == 0 else 1]
        query = human_query(position, self._moves, profile)
        allowed = self._chase.local_moves(self._moves, color)

        def read(answer: dict) -> Move:
            if allowed:
                return most_likely_among(answer, position.size, color, allowed)
            return most_likely_move(answer, position.size, color)

        self._plan.engine.query(query, self._receiver(read, self._moved))

    def _next_color(self) -> str:
        """Return the color to play next (the user's color plays first)."""
        next_color = self._plan.fight.position.next_color
        return next_color if len(self._moves) % 2 == 0 else opponent(next_color)

    def _moved(self, move: Move) -> None:
        """Add a move, and go on unless the sequence is complete."""
        places = fight_places(self._plan.fight, self._moves)
        self._moves = (*self._moves, move)
        self._on_move(self._moves)
        reason = self._stop_reason(move, places)
        if reason is None:
            self._ask_areas()
        else:
            self._finish(FollowEnd(reason))

    def _stop_reason(self, move: Move, places: list[Point]) -> str | None:
        """Return why the sequence ends after the move (an END_* value), or None to go on."""
        chasing, limits = self._chase.active, self._limits
        if move.coord is None:
            return END_PASS
        if not is_near(move, places):
            return END_LEFT
        if len(self._moves) >= (limits.chase_moves if chasing else limits.moves):
            return END_LENGTH
        if limits.clock() - self._started > (limits.chase_seconds if chasing else limits.seconds):
            return END_TIME
        return None

    def _finish(self, end: FollowEnd) -> None:
        """Log why the sequence ended, and tell it."""
        line = self._LOG_LINE
        record = {"line": line, "event": f"{line}_end", "moves": len(self._moves), "reason": end.reason}
        if end.reason == END_MIXED:
            record.update(black=end.black, white=end.white)
        else:
            record["color"] = end.color
        record["seconds"] = round(self._limits.clock() - self._started, 1)
        record["chase"] = self._chase.result
        record["chase_share"] = self._chase.share
        self._plan.log(record)
        self._on_done(self._moves, end)

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
        """End the sequence if the place is settled and no group is being chased, else ask for the next move."""
        self._chase.update(self._moves, areas)
        if not self._chase.active and self._plan.points and is_settled(areas, self._plan.points):
            self._finish(settled_end(self._plan.fight, areas, self._plan.points))
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
                line = self._LOG_LINE
                record = {"line": line, "event": f"{line}_error", "moves": len(self._moves), "message": str(error)}
                self._plan.log(record)
                self._on_error(str(error))
                return
            then(value)

        return receive


class _StrongFollowMaker(_FollowMaker):
    """Adds the moves of the strongest AI: each answer of KataGo has the best move and the areas of the position."""

    _LOG_LINE = "strong_follow"

    def __init__(self, plan: FollowPlan, limits: FollowLimits, on_move, on_done, on_error):
        """Keep what the sequence is made with (see _FollowMaker)."""
        super().__init__(plan, limits, on_move, on_done, on_error)
        self._restricted = False  # True while the query asked allows only the moves around the chased group.

    def ask_move(self) -> None:
        """Ask for the best move of the side to play (around the group, during a chase), with the areas."""
        plan = self._plan
        query = with_ownership(position_query(plan.fight.position, self._moves, plan.visits, plan.wide_root_noise))
        allowed = self._chase.local_moves(self._moves, self._next_color())
        self._restricted = bool(allowed)
        if allowed:
            query = with_allowed_moves(query, self._next_color(), allowed)
        plan.engine.query(query, self._receiver(self._read_answer, self._answered))

    def _read_answer(self, answer: dict) -> tuple[dict[Point, float], tuple[str, ...]]:
        """Return the areas and the best sequence of KataGo's answer (raises ValueError if it is an error)."""
        return self._read_areas(answer), best_sequence(answer)

    def _answered(self, read: tuple[dict[Point, float], tuple[str, ...]]) -> None:
        """Ask again if a chase has started or ended; else end the settled place, or play KataGo's best move."""
        areas, best = read
        plan = self._plan
        if self._moves:
            self._chase.update(self._moves, areas)
        allowed = self._chase.local_moves(self._moves, self._next_color())
        if bool(allowed) != self._restricted:
            self.ask_move()
        elif not allowed and self._moves and plan.points and is_settled(areas, plan.points):
            self._finish(settled_end(plan.fight, areas, plan.points))
        else:
            color = self._next_color()
            self._moved(Move.from_gtp(best[0], color) if best else Move(color, None))

    def _ask_areas(self) -> None:
        """Ask for the next move: its answer has the areas of the position too."""
        self.ask_move()
