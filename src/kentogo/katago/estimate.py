"""The territory and the standing at the end of a sequence (地と形勢), as KaTrain shows them.

The position at the end of a sequence and the game position after the same number of moves
are analyzed with few visits (the estimate_visits setting: a shallow reading is enough for the
territory), with the owner of each point. The standing tells the score lead at the end of the sequence,
and how much better (or worse) it is than the game after the same number of moves, for the
player who played the first move of the sequence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from kentogo.common.types import Move, Position, opponent
from kentogo.katago.evaluate import AnalysisEngine, EvaluationSettings
from kentogo.katago.queries import ownership_map, position_query, root_score, with_ownership

Point = tuple[int, int]


@dataclass(frozen=True)
class Estimate:
    """KataGo's view of one position.

    Attributes:
        lead: The score lead, from black's side.
        ownership: The owner of each point, from black's side (1: black, -1: white).
    """

    lead: float
    ownership: dict[Point, float]


@dataclass(frozen=True)
class Standing:
    """The standing at the end of a sequence.

    Attributes:
        end: The estimate at the end of the sequence.
        game: The estimate of the game after the same number of moves.
        color: The player who played the first move of the sequence.
    """

    end: Estimate
    game: Estimate
    color: str

    @property
    def gain(self) -> float:
        """How many points better the end of the sequence is than the game, for color."""
        difference = self.end.lead - self.game.lead
        return difference if self.color == "B" else -difference


def played(position: Position, moves: tuple[Move, ...]) -> Position:
    """Return the position after some more moves (the player to move is the other one after the last)."""
    if not moves:
        return position
    return replace(position, moves=position.moves + moves, next_color=opponent(moves[-1].color))


def estimate_standing(
    engine: AnalysisEngine,
    end: Position,
    game: Position,
    color: str,
    settings: EvaluationSettings,
    on_done: Callable[[Standing], None],
    on_error: Callable[[str], None],
) -> None:
    """Ask KataGo for the end of a sequence and the game position (two analyses with ownership).

    This returns at once. on_done or on_error is called once, in the engine's background thread.

    Args:
        engine: The KataGo engine.
        end: The position at the end of the sequence.
        game: The game position after the same number of moves.
        color: The player who played the first move of the sequence.
        settings: How KataGo analyzes: its estimate_visits and wide_root_noise are used.
        on_done: Called with the standing.
        on_error: Called with an error message.
    """
    found: dict[str, Estimate] = {}
    failed: list[str] = []

    def receiver(key: str, size: int) -> Callable[[dict], None]:
        """Return the callback of one analysis."""

        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch") or failed:
                return
            try:
                found[key] = Estimate(root_score(answer), ownership_map(answer, size))
            except ValueError as error:
                failed.append(str(error))
                on_error(str(error))
                return
            if len(found) == 2:
                on_done(Standing(found["end"], found["game"], color))

        return receive

    for key, position in (("end", end), ("game", game)):
        query = position_query(position, (), settings.estimate_visits, settings.wide_root_noise)
        query = with_ownership(query)
        engine.query(query, receiver(key, position.size))
