"""How big a move is, and what it does to the groups, from two readings: after the move, and after a pass.

Both positions have the opponent to play, so they can be compared point by point:

- points: the player's lead after the move minus the lead after a pass (what the player loses by
  leaving the move, "手抜きすると…目損").
- killed: the opponent's stones (still on the board after the move) that the opponent owns after a
  pass but the player owns after the move: the move kills them (life and death).
- saved: the player's stones that the opponent owns after a pass but the player owns after the move.
- on_stones: the part of the change of the owners that is on stones. A move that changes the owners
  of stones (a fight, life and death, a connection) is urgent (急場); a move that changes the owners
  of empty points is a big point (大場). This is only a guess (see kind_of).

KataGo reads each position with the visits of the territory and the standing (estimate_visits).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kentogo.common.board import Board
from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.queries import ownership_map, position_query, root_score, with_ownership

Point = tuple[int, int]
SURE_OWNER = 0.5  # An owner of a point at least this sure (from -1 to 1) owns it.
URGENT = "urgent"  # 急場
BIG = "big"  # 大場
URGENT_SHARE = 0.5  # A move whose change of the owners is at least this much on stones is urgent.


@dataclass(frozen=True)
class MoveValue:
    """What a move does, compared with a pass (see the module's docstring).

    Attributes:
        points: The player's lead after the move minus the lead after a pass.
        killed: The opponent's stones that the move kills.
        saved: The player's stones that the move saves.
        on_stones: The part (0 to 1) of the change of the owners that is on stones.
    """

    points: float
    killed: int
    saved: int
    on_stones: float


def kind_of(value: MoveValue) -> str:
    """Return URGENT for a move that kills, saves or changes the owners of stones most, else BIG (a guess)."""
    if value.killed or value.saved or value.on_stones >= URGENT_SHARE:
        return URGENT
    return BIG


def move_value(
    stones: dict[Point, str], color: str, after_move: tuple[float, dict[Point, float]], after_pass: tuple[float, dict]
) -> MoveValue:
    """Compare the readings after a move and after a pass.

    Args:
        stones: The stones on the board after the move (without the new stone), by point.
        color: The player of the move.
        after_move: Black's lead and the owners (from black's side) after the move.
        after_pass: Black's lead and the owners (from black's side) after a pass.
    """
    sign = 1.0 if color == "B" else -1.0
    move_owners, pass_owners = after_move[1], after_pass[1]
    changes = {point: (move_owners[point] - pass_owners[point]) * sign for point in move_owners}
    total = sum(abs(change) for change in changes.values())
    on_stones = sum(abs(changes[point]) for point in stones) / total if total else 0.0
    turned = [p for p in stones if pass_owners[p] * sign <= -SURE_OWNER and move_owners[p] * sign >= SURE_OWNER]
    killed = sum(1 for point in turned if stones[point] != color)
    return MoveValue((after_move[0] - after_pass[0]) * sign, killed, len(turned) - killed, on_stones)


def value_queries(position: Position, move: Move, visits: int, wide_root_noise: float | None) -> tuple[dict, dict]:
    """Return the queries of the position after the move and after a pass, with the owners of the points."""
    after_move = with_ownership(position_query(position, (move,), visits, wide_root_noise))
    after_pass = with_ownership(position_query(position, (Move(move.color, None),), visits, wide_root_noise))
    return after_move, after_pass


def read_move_value(
    engine: AnalysisEngine,
    position: Position,
    move: Move,
    visits: int,
    wide_root_noise: float | None,
    on_done: Callable[[MoveValue], None],
    on_error: Callable[[str], None],
) -> None:
    """Ask KataGo for both readings, and give the value when both have come (in KataGo's thread).

    Raises:
        IllegalMoveError: If the move cannot be played in the position.
    """
    board = Board.from_position(position)
    board.play(move)
    stones = {point: color for point, color in board.stones().items() if point != move.coord}
    readings: dict[str, tuple[float, dict]] = {}
    failed: list[str] = []  # The first error (the other answer is not used then).

    def receiver(name: str) -> Callable[[dict], None]:
        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch") or failed:
                return
            try:
                readings[name] = (root_score(answer), ownership_map(answer, position.size))
            except ValueError as error:
                failed.append(str(error))
                on_error(str(error))
                return
            if len(readings) == 2:
                on_done(move_value(stones, move.color, readings["move"], readings["pass"]))

        return receive

    after_move, after_pass = value_queries(position, move, visits, wide_root_noise)
    engine.query(after_move, receiver("move"))
    engine.query(after_pass, receiver("pass"))
