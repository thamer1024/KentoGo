"""How a local fight problem is played out and judged (see mistakes.local_fight): no KataGo here, only the rules.

The user plays the fight from where it started, and KataGo answers as the opponent, move after move (see
quiz.fight_run). After each move of the user, KataGo's areas (ownership, from black's side) of the position tell
whether the place is settled:

- The judged points are the stones that changed their owner in the game (the user's stones that died and the
  opponent's stones that lived) for a life and death fight, and the empty points that the user lost for a broken
  boundary (judged_points). Only those that are the user's at the start, in KataGo's reading with the best play,
  are judged (kept_points): a point that is lost whatever the user plays (the opponent's move into the user's
  area took it already) does not make the answer wrong. When none is left, only the score is judged.
- The place is settled when every judged point belongs to one side by at least SETTLED (is_settled).
- The fight is won when at least WIN_SHARE of the judged points are the user's by at least OWNED: the user's stones
  live, the opponent's stones die, or the user's territory is kept (fight_won).

The fight ends, and is judged, when:

- the place is settled: it is correct if the fight is won and the score did not fall by more than the tolerance
  (FightSettings.score_tolerance) since the start (OUTCOME_WON, OUTCOME_LOST or OUTCOME_SCORE);
- the user plays away from the fight (more than NEAR lines from the judged points and the fight's moves) or
  passes: it is wrong (OUTCOME_USER_LEFT);
- KataGo's best reply to the user's move is away from the fight (whoever plays the opponent): the place needs no
  more moves. If the user's move lost more than NEEDLESS_LOSS points, it was not needed either, and it is wrong
  (OUTCOME_OPPONENT_LEFT); otherwise the fight is judged as if settled. (A human-like opponent may still play
  away later while KataGo's best reply is in the fight: then the fight goes on.)
- the user has played the most moves (most_moves): it is judged as if settled (OUTCOME_WON, OUTCOME_LOST or
  OUTCOME_SCORE).

The score is KataGo's score lead from the user's side: at the start, and after the user's last move, read with
the same visits.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.common.types import Move
from kentogo.mistakes.local_fight import KIND_BOUNDARY, LocalFight

OWNED = 0.5  # A point is a player's when the ownership is at least this from the player's side.
SETTLED = 0.8  # The place is settled when every judged point is one side's by at least this.
WIN_SHARE = 0.8  # The fight is won when at least this share of the judged points are the user's.
NEAR = 3  # A move is in the fight when it is within this many lines of a judged point or a move of the fight.
EXTRA_MOVES = 4  # The user may play this many moves more than in the game, before the fight is judged.
NEEDLESS_LOSS = 1.0  # A move that lost more than this many points, when the place needed no more moves, was needless.

OUTCOME_WON = "won"  # Settled for the user, and the score held.
OUTCOME_LOST = "lost"  # Settled (or ended) against the user.
OUTCOME_SCORE = "score"  # Won, but the score fell by more than the tolerance.
OUTCOME_USER_LEFT = "user_left"  # The user played away from the fight (or passed).
OUTCOME_OPPONENT_LEFT = "opponent_left"  # The strongest opponent left the fight before it was settled.

OPPONENT_STRONG = "strong"  # The opponent plays KataGo's best moves (the engine's visits).
OPPONENT_RANK = "rank"  # The opponent plays the human-like moves of the opponent's rank.
OPPONENTS = (OPPONENT_STRONG, OPPONENT_RANK)

Point = tuple[int, int]
Areas = dict[Point, float]


@dataclass(frozen=True)
class FightOutcome:
    """How a local fight ended.

    Attributes:
        kind: OUTCOME_WON, OUTCOME_LOST, OUTCOME_SCORE, OUTCOME_USER_LEFT or OUTCOME_OPPONENT_LEFT.
        score_loss: How many points the user's score fell since the start (negative: it rose), or None if not known.
    """

    kind: str
    score_loss: float | None = None

    @property
    def correct(self) -> bool:
        """True if the fight was played correctly."""
        return self.kind == OUTCOME_WON


def judged_points(fight: LocalFight) -> list[Point]:
    """Return the points whose owner judges the fight: the stones for life and death, the empty points for a boundary."""
    texts = fight.points if fight.kind == KIND_BOUNDARY else (*fight.mine, *fight.theirs)
    return [Move.from_gtp(text, "B").coord for text in texts]


def kept_points(points: list[Point], areas: Areas, color: str) -> list[Point]:
    """Return the points that are color's by at least OWNED in the areas (those the best play keeps)."""
    sign = 1.0 if color == "B" else -1.0
    return [point for point in points if sign * areas.get(point, 0.0) >= OWNED]


def is_settled(areas: Areas, points: list[Point]) -> bool:
    """True if every point belongs to one side by at least SETTLED."""
    return all(abs(areas.get(point, 0.0)) >= SETTLED for point in points)


def fight_won(areas: Areas, points: list[Point], color: str) -> bool:
    """True if at least WIN_SHARE of the points are color's by at least OWNED (also when there are no points)."""
    if not points:
        return True
    sign = 1.0 if color == "B" else -1.0
    owned = sum(sign * areas.get(point, 0.0) >= OWNED for point in points)
    return owned >= WIN_SHARE * len(points)


def is_near(move: Move, places: list[Point]) -> bool:
    """True if a move is on the board within NEAR lines of one of the places (a pass is not)."""
    if move.coord is None:
        return False
    x, y = move.coord
    return any(max(abs(x - px), abs(y - py)) <= NEAR for px, py in places)


def fight_places(fight: LocalFight, played: tuple[Move, ...]) -> list[Point]:
    """Return the places of a fight: the judged points, the game's moves of the fight, and the moves played so far."""
    moves = (*fight.game_line[: fight.moves], *played)
    return judged_points(fight) + [move.coord for move in moves if move.coord is not None]


def most_moves(fight: LocalFight) -> int:
    """Return the most moves the user may play: the user's moves of the fight in the game, and EXTRA_MOVES."""
    return (fight.moves + 1) // 2 + EXTRA_MOVES


def score_loss(start_lead: float, end_lead: float, color: str) -> float:
    """Return how many points color's score fell from start_lead to end_lead (black's leads)."""
    sign = 1.0 if color == "B" else -1.0
    return sign * (start_lead - end_lead)


def ended_outcome(areas: Areas, points: list[Point], color: str, loss: float | None, tolerance: float) -> FightOutcome:
    """Return the outcome of a fight that ended (settled, needing no more moves, or the user played the most moves).

    Args:
        areas: KataGo's areas after the user's last move.
        points: The judged points (see kept_points).
        color: The user's color.
        loss: How many points the user's score fell since the start, or None if not known (then it is not used).
        tolerance: How many points the score may fall in a correct answer.
    """
    if not fight_won(areas, points, color):
        return FightOutcome(OUTCOME_LOST, loss)
    if loss is not None and loss > tolerance:
        return FightOutcome(OUTCOME_SCORE, loss)
    return FightOutcome(OUTCOME_WON, loss)
