"""How a local fight problem is played out and judged (see mistakes.local_fight): no KataGo here, only the rules.

The user plays the fight from where it started, and KataGo answers as the opponent, move after move (see
quiz.fight_run). After each move of the user, KataGo's areas (ownership, from black's side) of the position tell
whether the place is settled:

- The judged points are the stones that changed their owner in the game (the user's stones that died and the
  opponent's stones that lived) for a life and death fight, and the empty points that the user lost for a broken
  boundary (judged_points).
- The place is settled when every judged point belongs to one side by at least SETTLED (is_settled).
- The fight is won when at least WIN_SHARE of the judged points are the user's by at least OWNED: the user's stones
  live, the opponent's stones die, or the user's territory is kept (fight_won).

The fight ends, and is judged, when:

- the place is settled: it is correct if the fight is won and the score did not fall by more than the tolerance
  (FightSettings.score_tolerance) since the start (OUTCOME_WON, OUTCOME_LOST or OUTCOME_SCORE);
- the strongest opponent plays away from the fight, after a move of the user in the fight, while the place is not
  settled: the user's move did not need an answer, so it is wrong (OUTCOME_OPPONENT_LEFT; a human-like opponent
  may leave, and the fight goes on);
- the user has played the most moves (most_moves): it is judged as if settled (OUTCOME_WON, OUTCOME_LOST or
  OUTCOME_SCORE).

The user may play away from the fight (more than NEAR lines from the fight's places, see fight_places) or pass:
such a move is read and judged as any other, so it is correct when the place is settled for the user anyway
(FightOutcome.left tells it). After it, the opponent may answer away from the fight too (the user's move was
sente there), and the fight goes on.

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

OUTCOME_WON = "won"  # Settled for the user, and the score held.
OUTCOME_LOST = "lost"  # Settled (or ended) against the user.
OUTCOME_SCORE = "score"  # Won, but the score fell by more than the tolerance.
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
        kind: OUTCOME_WON, OUTCOME_LOST, OUTCOME_SCORE or OUTCOME_OPPONENT_LEFT.
        score_loss: How many points the user's score fell since the start (negative: it rose), or None if not known.
        left: True if the user's last move was away from the fight (or a pass).
    """

    kind: str
    score_loss: float | None = None
    left: bool = False

    @property
    def correct(self) -> bool:
        """True if the fight was played correctly."""
        return self.kind == OUTCOME_WON


def judged_points(fight: LocalFight) -> list[Point]:
    """Return the points whose owner judges the fight: the stones for life and death, the empty points for a boundary."""
    texts = fight.points if fight.kind == KIND_BOUNDARY else (*fight.mine, *fight.theirs)
    return [Move.from_gtp(text, "B").coord for text in texts]


def is_settled(areas: Areas, points: list[Point]) -> bool:
    """True if every point belongs to one side by at least SETTLED."""
    return all(abs(areas.get(point, 0.0)) >= SETTLED for point in points)


def fight_won(areas: Areas, points: list[Point], color: str) -> bool:
    """True if at least WIN_SHARE of the points are color's by at least OWNED."""
    if not points:
        return False
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
    """Return the places of a fight: the judged points, the game's moves of the fight, and the moves played in it.

    A move played is in the fight when it is near the places before it: the moves away from the fight (and the
    answers to them) are not.
    """
    places = judged_points(fight) + [move.coord for move in fight.game_line[: fight.moves] if move.coord is not None]
    for move in played:
        if is_near(move, places):
            places.append(move.coord)
    return places


def most_moves(fight: LocalFight) -> int:
    """Return the most moves the user may play: the user's moves of the fight in the game, and EXTRA_MOVES."""
    return (fight.moves + 1) // 2 + EXTRA_MOVES


def score_loss(start_lead: float, end_lead: float, color: str) -> float:
    """Return how many points color's score fell from start_lead to end_lead (black's leads)."""
    sign = 1.0 if color == "B" else -1.0
    return sign * (start_lead - end_lead)


def ended_outcome(areas: Areas, fight: LocalFight, loss: float | None, tolerance: float) -> FightOutcome:
    """Return the outcome of a fight that ended (settled, or the user played the most moves).

    Args:
        areas: KataGo's areas after the user's last move.
        fight: The fight.
        loss: How many points the user's score fell since the start, or None if not known (then it is not used).
        tolerance: How many points the score may fall in a correct answer.
    """
    if not fight_won(areas, judged_points(fight), fight.position.next_color):
        return FightOutcome(OUTCOME_LOST, loss)
    if loss is not None and loss > tolerance:
        return FightOutcome(OUTCOME_SCORE, loss)
    return FightOutcome(OUTCOME_WON, loss)
