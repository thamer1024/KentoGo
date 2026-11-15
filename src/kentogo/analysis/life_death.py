"""Find the local fights that the user lost: life and death, and broken boundaries, from KataGo's areas.

A move of the user changes the owner of a place when, by KataGo's areas (ownership, from black's side), points
went over from the user to the opponent with the move. In the position before the move (the user to play, so the
areas are those of the best play) the points were the user's by at least OWNED, and in the position after it (the
opponent to play):

- Stones (on the board after the move) are the opponent's by at least OWNED: the user's own stones died, or the
  opponent's stones lived (the user did not kill them). With at least MIN_STONES such stones, the move lost a
  life and death fight (KIND_LIFE_DEATH). The size of the loss is not used: a group can die in a game that is
  decided already, or for few points.
- Otherwise, empty points are no longer the user's (their ownership from the user's side is at most 0): with at
  least MIN_POINTS of them, and a loss of at least MIN_BOUNDARY_LOSS points (a territory given for something
  bigger is no mistake), the move let a boundary be broken (KIND_BOUNDARY).

The problem starts where the fight started (see fight_start): from the move, the moves near the changed points
(within NEAR lines) are followed back, at most WALK_BACK moves, and the first move of the opponent into the user's
area (a point that was the user's before it) starts the problem. When there is none, the problem starts just before
the user's move. The user is then to play in the problem's position.

The moves are found with the areas of the first, shallow analysis, which are rough. At most LOCAL_FIGHT_MOVES of
them are read again deeply (see analysis.analyze.read_local_fights), and only those that still change the owner of
the place are kept, in the analysis data of the node where the problem starts ("local_fight", see as_data).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pysgf import GoNode

from kentogo.common.board import Board, IllegalMoveError, Point
from kentogo.common.types import Move, Position
from kentogo.katago.queries import ownership_map
from kentogo.record.kentogo_analysis import KIND_BOUNDARY, KIND_LIFE_DEATH

OWNED = 0.5  # A point is a player's when KataGo's ownership is at least this from the player's side.
MIN_STONES = 3  # The fewest stones that must change their owner in a life and death fight.
MIN_POINTS = 5  # The fewest empty points that the user must lose when a boundary is broken.
MIN_BOUNDARY_LOSS = 2.0  # The smallest loss (points) of a move that let a boundary be broken.
NEAR = 2  # A move is in the fight when it is within this many lines of a changed point.
WALK_BACK = 10  # The most moves followed back to find where the fight started.
LOCAL_FIGHT_MOVES = 3  # The most moves of a game read deeply to find the local fights.

Areas = dict[Point, float]  # KataGo's ownership by point, from black's side.


@dataclass(frozen=True)
class LocalChange:
    """The points that went over to the opponent with a move of the user (GTP points, in the order of the points).

    Attributes:
        kind: KIND_LIFE_DEATH or KIND_BOUNDARY.
        mine: The user's stones that died by the move.
        theirs: The opponent's stones that lived by the move (the user did not kill them).
        points: The empty points that were the user's and are no longer.
    """

    kind: str
    mine: tuple[str, ...]
    theirs: tuple[str, ...]
    points: tuple[str, ...]

    @property
    def size(self) -> int:
        """Return how many points changed their owner (stones and empty points)."""
        return len(self.mine) + len(self.theirs) + len(self.points)

    def coords(self) -> list[Point]:
        """Return the changed points as (x, y)."""
        return [Move.from_gtp(text, "B").coord for text in (*self.mine, *self.theirs, *self.points)]

    def as_data(self, moves: int) -> dict:
        """Return the data kept where the problem starts ("local_fight").

        Args:
            moves: How many moves of the game there are from the problem's position to the user's move that lost
                the fight, that move included.
        """
        return {
            "kind": self.kind,
            "mine": list(self.mine),
            "theirs": list(self.theirs),
            "points": list(self.points),
            "moves": moves,
        }


def local_change(stones: dict[Point, str], before: Areas, after: Areas, player: str, loss: float) -> LocalChange | None:
    """Return what went over to the opponent of player with a move, or None when it is not a lost fight.

    Args:
        stones: The stones on the board after the move, by point.
        before: KataGo's ownership (from black's side) in the position before the move.
        after: KataGo's ownership (from black's side) in the position after the move.
        player: The color of the user, who played the move.
        loss: The points lost by the move (for a broken boundary).
    """
    sign = 1.0 if player == "B" else -1.0
    mine, theirs, points = [], [], []
    for point in sorted(before):
        if sign * before[point] < OWNED:
            continue
        mine_after = sign * after.get(point, 0.0)
        color = stones.get(point)
        if color is not None and mine_after <= -OWNED:
            (mine if color == player else theirs).append(Move(color, point).gtp())
        elif color is None and mine_after <= 0.0:
            points.append(Move(player, point).gtp())
    if len(mine) + len(theirs) >= MIN_STONES:
        return LocalChange(KIND_LIFE_DEATH, tuple(mine), tuple(theirs), tuple(points))
    if len(points) >= MIN_POINTS and loss >= MIN_BOUNDARY_LOSS:
        return LocalChange(KIND_BOUNDARY, tuple(mine), tuple(theirs), tuple(points))
    return None


def change_of(node: GoNode, before: dict | None, after: dict | None, loss: float | None) -> LocalChange | None:
    """Return what went over to the opponent with a node's move (see local_change), or None.

    Args:
        node: The node of the move (its player is the user).
        before: The analysis of the position before the move (with "ownership"), or None.
        after: The analysis of the position after the move (with "ownership"), or None.
        loss: The points lost by the move, or None when not known (0 is used).

    Returns:
        None too when an analysis or its areas are missing, the board is not square, or the moves cannot be
        played on the board.
    """
    move = node.move
    before_areas, after_areas = areas_of(node, before), areas_of(node, after)
    if move is None or before_areas is None or after_areas is None:
        return None
    try:
        stones = stones_after(node)
    except IllegalMoveError:
        return None
    return local_change(stones, before_areas, after_areas, move.player, loss or 0.0)


def areas_of(node: GoNode, analysis: dict | None) -> Areas | None:
    """Return the areas of an analysis of a position of the node's game, or None (no areas, or not a square board)."""
    size_x, size_y = node.board_size
    if size_x != size_y:
        return None
    try:
        return ownership_map({"ownership": list((analysis or {}).get("ownership") or ())}, size_x)
    except ValueError:
        return None


def fight_start(node: GoNode, change: LocalChange, areas: Callable[[GoNode], Areas | None]) -> GoNode:
    """Return the node after which the problem of a lost fight starts (see the module's docstring).

    Args:
        node: The user's move that lost the fight.
        change: What went over to the opponent with it.
        areas: The areas of the position after a node (from black's side), or None when not known.

    Returns:
        The opponent's first move into the user's area, or the node before the user's move.
    """
    player = node.move.player
    sign = 1.0 if player == "B" else -1.0
    changed = change.coords()
    start = node.parent
    current = node
    for _ in range(WALK_BACK):
        current = current.parent
        if current is None or current.parent is None or not _near(current, changed):
            break
        move = current.move
        before = areas(current.parent)
        if move.player != player and before is not None and sign * before.get(move.coords, 0.0) >= OWNED:
            start = current
    return start


def strongest_changes(found: Iterable[tuple[GoNode, LocalChange]], limit: int) -> list[GoNode]:
    """Return the nodes whose moves changed the most points (at most limit), in the order of the game.

    Of two moves that changed as many points, the earlier one is taken.
    """
    listed = list(found)
    order = sorted(range(len(listed)), key=lambda index: (-listed[index][1].size, index))
    chosen = set(order[:limit])
    return [node for index, (node, _) in enumerate(listed) if index in chosen]


def stones_after(node: GoNode) -> dict[Point, str]:
    """Return the stones on the board after a node's move, by point (the captured stones are removed).

    Raises:
        IllegalMoveError: If the moves cannot be played on the board.
    """
    nodes = node.nodes_from_root
    setup = tuple(Move(stone.player, stone.coords) for item in nodes for stone in item.placements)
    moves = tuple(Move(move.player, move.coords) for item in nodes for move in item.moves)
    position = Position(node.board_size[0], node.komi, node.ruleset, setup, moves, "B")
    return Board.from_position(position).stones()


def _near(node: GoNode, points: list[Point]) -> bool:
    """True if a node's move is on the board within NEAR lines of one of the points."""
    move = node.move
    if move is None or move.coords is None:
        return False
    x, y = move.coords
    return any(max(abs(x - px), abs(y - py)) <= NEAR for px, py in points)
