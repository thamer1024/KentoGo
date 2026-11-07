"""How one move changes the areas: the game move against the best move (the "地の違い" view, D).

When a game was analyzed by KentoGo (see analysis.analyze), the moves that can become problems
were read deeply, and KentoGo's own data (KGD, see record.kentogo_data) keeps KataGo's areas
(ownership) after the best move ("best_after"); the areas after the game move are in the analysis
data of the move's node (KT, kept whole for such moves). So the change is shown without KataGo.

The view goes through three pictures: the areas after the game move, the areas after the best
move, and the points whose owner changes (CHANGED: the owner's sign changes, by at least CHANGED
on KataGo's scale from -1 to 1), each from black's side, with the board changed as the problem
is (see AreaChange.transformed).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from kentogo.common import sgf
from kentogo.common.types import Move
from kentogo.katago.queries import ownership_map
from kentogo.mistakes.problem import Problem
from kentogo.quiz.transform import BoardTransform
from kentogo.record.katrain_kt import decode_kt_numbers
from kentogo.record.kentogo_data import read_kgd

Point = tuple[int, int]
CHANGED = 0.5  # A point changes owner when the sign changes and the value moves at least this much.

# What the view shows (AreaView.mode), in the order of D.
AREAS_OFF = 0
AREAS_PLAYED = 1  # The areas after the game move.
AREAS_BEST = 2  # The areas after the best move.
AREAS_CHANGE = 3  # The points whose owner changes.
AREA_MODES = (AREAS_OFF, AREAS_PLAYED, AREAS_BEST, AREAS_CHANGE)


@dataclass(frozen=True)
class AreaChange:
    """The areas after the game move and after the best move of a problem, from black's side.

    Attributes:
        played: The game move.
        best: KataGo's best move.
        played_areas: The owner of each point after the game move (1: black, -1: white).
        best_areas: The owner of each point after the best move.
        played_lead: Black's lead after the game move, or None if unknown.
        best_lead: Black's lead after the best move, or None if unknown.
    """

    played: Move
    best: Move
    played_areas: dict[Point, float]
    best_areas: dict[Point, float]
    played_lead: float | None
    best_lead: float | None

    def changed(self) -> dict[Point, float]:
        """Return the points whose owner changes, with the change from the game move to the best move."""
        found = {}
        for point, best in self.best_areas.items():
            played = self.played_areas.get(point, 0.0)
            if played * best < 0 and abs(best - played) >= CHANGED:
                found[point] = best - played
        return found

    def gained(self, color: str) -> int:
        """Return how many points change to the color's owner with the best move (fewer than 0: to the other)."""
        sign = 1 if color == "B" else -1
        return sum(1 if value * sign > 0 else -1 for value in self.changed().values())

    def lead_gain(self, color: str) -> float | None:
        """Return how many points the best move is better for the color than the game move, or None."""
        if self.played_lead is None or self.best_lead is None:
            return None
        return (self.best_lead - self.played_lead) * (1 if color == "B" else -1)

    def transformed(self, transform: BoardTransform, size: int) -> AreaChange:
        """Return the change as the problem is shown: the points move, and the sides swap with the colors."""
        sign = -1.0 if transform.swap_colors else 1.0

        def areas(values: dict[Point, float]) -> dict[Point, float]:
            return {transform.point(point, size): value * sign for point, value in values.items()}

        def lead(value: float | None) -> float | None:
            return None if value is None else value * sign

        return replace(
            self,
            played=transform.move(self.played, size),
            best=transform.move(self.best, size),
            played_areas=areas(self.played_areas),
            best_areas=areas(self.best_areas),
            played_lead=lead(self.played_lead),
            best_lead=lead(self.best_lead),
        )


def read_area_change(problem: Problem) -> AreaChange | None:
    """Read the change of the areas of a problem from its SGF file, or None when the game has no such data.

    The data is there when the game was analyzed by KentoGo and the move was read deeply.

    Raises:
        OSError: If the file cannot be read.
    """
    root = sgf.load_game(Path(problem.sgf_path))
    node = _problem_node(root, problem)
    if node is None:
        return None
    data = read_kgd(node)
    best_after = (data or {}).get("best_after", {})
    best = (data or {}).get("best", {}).get("move")
    size = problem.position.size
    kt = node.get_list_property("KT", [])
    if not best or best == "pass" or "ownership" not in best_after or not kt:
        return None
    try:
        played_ownership = decode_kt_numbers(kt, size * size)[0]
    except ValueError:
        return None
    if played_ownership is None:
        return None
    return AreaChange(
        played=problem.actual_move,
        best=Move.from_gtp(best, problem.actual_move.color),
        played_areas=ownership_map({"ownership": list(played_ownership)}, size),
        best_areas=ownership_map({"ownership": list(best_after["ownership"].values)}, size),
        played_lead=data.get("played_after", {}).get("scoreLead"),
        best_lead=best_after.get("scoreLead"),
    )


def _problem_node(root, problem: Problem):
    """Return the node of the problem's move (in the main line or a branch), or None."""
    for node in root.nodes_in_tree:
        if node.depth == problem.move_number and sgf.node_move(node) == problem.actual_move:
            return node
    return None


@dataclass
class AreaView:
    """What the "地の違い" view of one problem shows (D goes through AREA_MODES).

    Attributes:
        problem: The problem (as in the SGF file).
        change: The change, once read (None: not read yet, or the game has no data; see missing).
        missing: True when the game has no data for it.
        mode: One of AREA_MODES.
    """

    problem: Problem
    change: AreaChange | None = None
    missing: bool = False
    mode: int = AREAS_OFF

    def next(self) -> int:
        """Show the next picture (reading the data the first time); return the new mode (AREAS_OFF without data)."""
        if self.change is None and not self.missing:
            self.change = read_area_change(self.problem)
            self.missing = self.change is None
        if self.missing:
            self.mode = AREAS_OFF
            return self.mode
        self.mode = AREA_MODES[(AREA_MODES.index(self.mode) + 1) % len(AREA_MODES)]
        return self.mode

    def hide(self) -> None:
        """Stop showing the areas."""
        self.mode = AREAS_OFF
