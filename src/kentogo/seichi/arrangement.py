"""The stones on the board while the user arranges the territory (seichi).

The user moves a stone to an empty point, or swaps two stones of different colors.
This module keeps the stones and the history of the changes, without Kivy, so
that it can be tested. Every change can be taken back (undo), and the board can
go back to the final position (reset).

Arranging must not change the territory of either player (counted with the
Japanese rules, see territory). A move that would change it is not made, and
TerritoryChangedError tells the counts before and after it.

The user marks dead stones by clicking them (a whole connected group at a time).
Dead stones are counted as if they were not on the board, so the area around them
becomes the territory of the player who surrounds them. Marking changes the
territory on purpose, so it is not checked; it can be taken back like a move.

Open dame (empty points between the territories) join a territory to the other
color's stones, so that area would count for no one. The user fills them with
stones by clicking them (fill_dame), as players do at the end of a game. A dame
may be filled only when the stone does not put a group in atari (so that no
more moves would be needed), and only on a point that is not territory.

The dead stones are taken off by the user too (remove_dead, or take_off_dead for
one stone). When no stone is marked dead and every empty point is territory, the
computer can do the rest of the seichi (auto_fill).

Prisoners (agehama) are the stones captured during the game, and the dead stones
when they are taken off the board (remove_dead). They wait in a tray for each
color, and the user puts them on the board: a prisoner may be put only on a point
of the territory of its own color (a white prisoner fills white's territory), so
the result of the game does not change. Several prisoners can be put at once:
they fill the empty area of the territory where they are dropped, from the points
nearest the edge of the board. A prisoner put on the board can be taken back to
its tray.

auto_fill does the rest of the seichi as the computer would, as a person does it: it
takes off the stones that have no liberty, puts the prisoners into the territory, and
then makes each player's territory rectangles of whole tens where it is, moving only the
players' own stones; the territory stays the same (see block_tidy). At the end, black and white
stones are swapped to make the boundary clear (see boundary). Each step is kept (FillResult.steps),
so that the screen can show the seichi one step at a time. auto_fill is done once:
after it, ready_for_auto is False until it is taken back.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from kentogo.common.board import Board
from kentogo.common.types import Position
from kentogo.seichi.auto_fill import fill_points
from kentogo.seichi.block_tidy import TidyMove, tidy_color
from kentogo.seichi.boundary import clear_boundary
from kentogo.seichi.count_check import CountCheck, right_territory
from kentogo.seichi.seki import neutral_points
from kentogo.seichi.stray_stones import stray_stones
from kentogo.seichi.territory import TerritoryCount, count_territory, majority_owners, territory_owners

Point = tuple[int, int]


class TerritoryChangedError(ValueError):
    """Raised when a move would change the territory of a player. The move is not made.

    Attributes:
        before: The territory before the move.
        after: The territory the move would make.
    """

    def __init__(self, before: TerritoryCount, after: TerritoryCount):
        """Keep the counts before and after the move."""
        super().__init__(f"the territory would change from {before} to {after}")
        self.before = before
        self.after = after


@dataclass(frozen=True)
class _State:
    """The stones and the dead marks at one time (kept in the history for undo)."""

    stones: dict[Point, str]
    dead: frozenset[Point] = frozenset()
    placed: frozenset[Point] = frozenset()  # Prisoners put on the board from a tray.
    filled: frozenset[Point] = frozenset()  # Dame filled with stones by the user.
    prisoners: tuple[tuple[str, int], ...] = (("B", 0), ("W", 0))  # Stones of each color in the trays.
    auto: bool = False  # True after the computer's seichi (auto_fill), until it is taken back.
    removed: frozenset[Point] = frozenset()  # Dead stones taken off the board (where they were).
    confirmed: _Confirmed | None = None  # Set when the end of the game is confirmed (the seichi phase).
    marks: dict[Point, str] = field(default_factory=dict)  # Owners set by the user in the seichi phase.

    @property
    def prisoner_counts(self) -> dict[str, int]:
        """The number of prisoners of each color in the trays, as {"B": n, "W": n}."""
        return dict(self.prisoners)

    def with_prisoners(self, counts: dict[str, int]) -> _State:
        """Return this state with other prisoner counts."""
        return replace(self, prisoners=(("B", counts["B"]), ("W", counts["W"])))

    @property
    def live_stones(self) -> dict[Point, str]:
        """The stones that are not marked dead."""
        return {point: color for point, color in self.stones.items() if point not in self.dead}


@dataclass(frozen=True)
class _Confirmed:
    """What was known when the end of the game was confirmed (see Arrangement.confirm).

    Attributes:
        count: The territory of each player then: the result that the seichi keeps.
        owners: The owner of each point of territory then. A point keeps this owner when the
            stones around it no longer show it (for example after a stone of the boundary moved).
        state: The state just before, from which the computer's seichi starts.
    """

    count: TerritoryCount
    owners: dict[Point, str]
    state: _State


@dataclass(frozen=True)
class FillStep:
    """One step of the computer's seichi, and the board after it.

    Attributes:
        kind: "capture" (stones without liberty taken off), "move" (a stone moved), "place" (a
            prisoner put into the territory), or "swap" (a black stone and a white stone swapped at
            the end, to make the boundary clear; see boundary). The screen also knows "exchange" (a
            stone moved and changed to the other color).
        color: The color of the stone of the step (before it changes; the first stone of a swap).
        points: The points of the step: the stones taken off, the prisoner, or (from, to).
        stones: The stones after the step.
        prisoners: The prisoners of each color in the trays after the step.
    """

    kind: str
    color: str
    points: tuple[Point, ...]
    stones: dict[Point, str]
    prisoners: dict[str, int]


@dataclass(frozen=True)
class FillResult:
    """What auto_fill left: the areas of territory of each color, and the prisoners that did not fit.

    Attributes:
        areas: The sizes of the areas of each color, the largest first, as {"B": [...], "W": [...]}.
        left: The prisoners of each color still in the trays (when the territory was too small).
        captured: The stones of each color that had no liberty and were taken off as prisoners first.
        start: The stones before the computer's seichi.
        steps: The steps, in order (the last one gives the stones now).
        start_prisoners: The prisoners of each color in the trays before the computer's seichi.
    """

    areas: dict[str, list[int]]
    left: dict[str, int]
    captured: dict[str, int] = field(default_factory=lambda: {"B": 0, "W": 0})
    start: dict[Point, str] = field(default_factory=dict)
    steps: list[FillStep] = field(default_factory=list)
    start_prisoners: dict[str, int] = field(default_factory=lambda: {"B": 0, "W": 0})


@dataclass(frozen=True)
class AutoPlan:
    """The computer's seichi, found by Arrangement.plan_auto and put on the board by use_auto.

    Attributes:
        before: The state it was planned from.
        after: The state after it.
        result: What it gives (see FillResult).
    """

    before: _State
    after: _State
    result: FillResult


class PlacementError(ValueError):
    """Raised when a prisoner cannot be put on a point. The message is a key of the screen texts."""


class Arrangement:
    """The stones of a board that the user arranges.

    Attributes:
        size: The number of lines of the board.
    """

    def __init__(self, position: Position):
        """Start from the final position of a game.

        Args:
            position: The final position (all moves played, captured stones removed).
        """
        self.size = position.size
        board = Board.from_position(position)
        # board.captures counts the stones each player captured: the white stones that black holds, and so on.
        prisoners = (("B", board.captures["W"]), ("W", board.captures["B"]))
        self._start = _State(board.stones(), prisoners=prisoners)
        self._state = self._start
        self._history: list[_State] = []

    @property
    def stones(self) -> dict[Point, str]:
        """The stones now (dead ones too), as a new dict from point to "B" or "W"."""
        return dict(self._state.stones)

    @property
    def dead(self) -> frozenset[Point]:
        """The points of the stones marked dead."""
        return self._state.dead

    @property
    def filled_dame(self) -> frozenset[Point]:
        """The points of the dame filled with stones by the user."""
        return self._state.filled

    @property
    def neutral(self) -> frozenset[Point]:
        """The points that are not territory because of seki (or false eyes), see seki.neutral_points.

        They are found on the final position, with the stones marked dead or taken off as dead.
        """
        state = self._state
        return neutral_points(self.size, self._start.stones, state.dead | state.removed)

    @property
    def territory_points(self) -> dict[Point, str]:
        """The owner of each point of territory now, as {point: "B" or "W"}.

        Before the end is confirmed, an empty area belongs to the color that surrounds it. In the
        seichi phase, an empty point that the stones no longer show as anyone's keeps the owner
        it had when the end was confirmed, and the user's marks (mark_area) come before both.
        """
        state = self._state
        owners = territory_owners(self.size, state.live_stones, neutral=self.neutral)
        if state.confirmed is None:
            return owners
        for point in self._empty_points():
            if point not in owners and point in state.confirmed.owners:
                owners[point] = state.confirmed.owners[point]
        for point, owner in state.marks.items():
            if point in state.stones:
                continue  # A stone stands there now.
            if owner:
                owners[point] = owner
            else:
                owners.pop(point, None)
        return owners

    @property
    def in_seichi(self) -> bool:
        """True after the end of the game was confirmed: the stones may be moved freely."""
        return self._state.confirmed is not None

    @property
    def confirmed_count(self) -> TerritoryCount | None:
        """The territory when the end was confirmed, or None before it."""
        confirmed = self._state.confirmed
        return confirmed.count if confirmed is not None else None

    def check_count(self) -> CountCheck:
        """Check the user's seichi (see count_check).

        Raises:
            PlacementError: If the end of the game has not been confirmed ("count_not_seichi").
        """
        confirmed = self._state.confirmed
        if confirmed is None:
            raise PlacementError("count_not_seichi")
        right = right_territory(confirmed.count, confirmed.state.prisoner_counts)
        owners = list(majority_owners(self.size, self._state.live_stones, self.neutral).values())
        board = TerritoryCount(owners.count("B"), owners.count("W"))
        return CountCheck(right, board, dict(self._state.prisoner_counts))

    @property
    def ready_to_confirm(self) -> bool:
        """True when the end can be confirmed: no stone marked dead, and every dame filled."""
        return not self.in_seichi and not self._state.dead and not self.open_dame

    @property
    def undecided(self) -> set[Point]:
        """In the seichi phase, the empty points that are nobody's yet and not set by the user."""
        if not self.in_seichi:
            return set()
        owners = self.territory_points
        marks = self._state.marks
        return {point for point in self._empty_points() if point not in owners and point not in marks}

    def confirm(self) -> None:
        """Confirm the end of the game, and start the seichi phase.

        From then on the territory that was counted is kept (confirmed_count), and moves are not
        checked: as people do, the stones of the boundary may be moved too.

        Raises:
            PlacementError: If dead stones are still marked or dame are open ("confirm_not_ready").
        """
        if not self.ready_to_confirm:
            raise PlacementError("confirm_not_ready")
        self._change(replace(self._state, confirmed=self._confirmation()))

    def mark_area(self, point: Point) -> str:
        """In the seichi phase, set who owns an empty point and the empty points connected to it.

        The connected empty points that have the same owner now (or none) change together, in the
        order black, white, nobody, black, ... The user uses it when the stones no longer show it.
        A point that goscorer did not count (seki, or a false eye, see seki) can be set too: the
        user decides in the end, as people do.

        Returns:
            The new owner: "B", "W" or "" (nobody).

        Raises:
            PlacementError: Before the seichi phase ("mark_not_seichi"), or on a stone ("mark_not_empty").
        """
        state = self._state
        if state.confirmed is None:
            raise PlacementError("mark_not_seichi")
        if point in state.stones or not self._on_board(point):
            raise PlacementError("mark_not_empty")
        owners = self.territory_points
        now = owners.get(point)
        new = {"B": "W", "W": ""}.get(now, "B")
        area = _same_owner_area(point, owners, set(self._empty_points()))
        self._change(replace(state, marks={**state.marks, **dict.fromkeys(area, new)}))
        return new

    def _confirmation(self) -> _Confirmed:
        """Return what is known now, as it is kept when the end is confirmed."""
        return _Confirmed(self.territory, dict(self.territory_points), self._state)

    def _empty_points(self) -> list[Point]:
        """The empty points of the board that are not points of seki."""
        stones, neutral = self._state.stones, self.neutral
        size = range(self.size)
        return [(x, y) for x in size for y in size if (x, y) not in stones and (x, y) not in neutral]

    @property
    def open_dame(self) -> set[Point]:
        """The empty points that are not territory (dame that are not filled yet), but not those of seki."""
        owners = self.territory_points
        stones = self._state.stones
        neutral = self.neutral
        size = range(self.size)
        return {
            (x, y)
            for x in size
            for y in size
            if (x, y) not in stones and (x, y) not in owners and (x, y) not in neutral
        }

    @property
    def ready_for_auto(self) -> bool:
        """True when the computer's seichi can be done: in the seichi phase (or ready to confirm), before auto_fill."""
        return not self._state.auto and (self.in_seichi or self.ready_to_confirm)

    @property
    def auto_done(self) -> bool:
        """True after the computer's seichi (auto_fill), until it is taken back."""
        return self._state.auto

    @property
    def placed(self) -> frozenset[Point]:
        """The points of the prisoners put on the board."""
        return self._state.placed

    @property
    def prisoners(self) -> dict[str, int]:
        """The number of prisoners of each color in the trays, as {"B": n, "W": n}."""
        return self._state.prisoner_counts

    @property
    def territory(self) -> TerritoryCount:
        """The territory of each player now (dead stones are counted as not on the board; see territory_points)."""
        owners = list(self.territory_points.values())
        return TerritoryCount(owners.count("B"), owners.count("W"))

    @property
    def pending_prisoners(self) -> dict[str, int]:
        """The stones marked dead, by color: they become prisoners when they are taken off."""
        stones = self._state.stones
        colors = [stones[point] for point in self._state.dead]
        return {"B": colors.count("B"), "W": colors.count("W")}

    @property
    def margin(self) -> int:
        """Black's lead now, without komi: territory and prisoners held of each player (Japanese rules).

        Black holds the white prisoners (in the tray, and the white stones marked dead), and white
        holds the black ones. Prisoners already put into the territory have made it smaller instead.
        So the seichi never changes this number: it is a check of the counting.
        """
        territory, trays, pending = self.territory, self.prisoners, self.pending_prisoners
        black = territory.black + trays["W"] + pending["W"]
        white = territory.white + trays["B"] + pending["B"]
        return black - white

    @property
    def can_undo(self) -> bool:
        """True if there is a change to take back."""
        return bool(self._history)

    def toggle_dead(self, point: Point) -> bool:
        """Mark the group of stones at a point as dead, or as alive again if it is marked dead.

        A group is the stones of the same color connected to the point (up, down, left, right).

        Returns:
            True if there was a stone at the point (and the end is not confirmed yet).
        """
        if point not in self._state.stones or self.in_seichi:
            return False
        group = self._group(point)
        dead = self._state.dead - group if point in self._state.dead else self._state.dead | group
        self._change(replace(self._state, dead=frozenset(dead)))
        return True

    def fill_dame(self, point: Point) -> str:
        """Fill a dame with a stone: black if that is safe, otherwise white.

        Raises:
            PlacementError: If the point is not an open dame ("dame_not_dame"), or a stone of either
                color there would put a group in atari ("dame_atari").

        Returns:
            The color of the stone.
        """
        if point not in self.open_dame:
            raise PlacementError("dame_not_dame")
        for color in ("B", "W"):
            stones = {**self._state.stones, point: color}
            if not _makes_atari(stones, point, self.size):
                self._change(replace(self._state, stones=stones, filled=self._state.filled | {point}))
                return color
        raise PlacementError("dame_atari")

    def remove_dame(self, point: Point) -> bool:
        """Take back a stone that filled a dame. Returns True if the point had one."""
        if point not in self._state.filled:
            return False
        stones = {other: color for other, color in self._state.stones.items() if other != point}
        self._change(replace(self._state, stones=stones, filled=self._state.filled - {point}))
        return True

    def move(self, source: Point, target: Point) -> bool:
        """Move the stone on source to target. If target has a stone of the other color, swap them.

        A dead mark moves with its stone.

        Args:
            source: The point of the stone to move.
            target: The point to put it on.

        Returns:
            True if the board changed. Nothing changes when source has no stone, target is
            outside the board or the same point, the stone filled a dame, or target has a stone of the
            same color.

        Raises:
            TerritoryChangedError: If the move would change the territory of a player (only before
                the end is confirmed; in the seichi phase any move is allowed). The move is not made.
        """
        stones = self._state.stones
        color = stones.get(source)
        if color is None or source == target or not self._on_board(target) or source in self._state.filled:
            return False
        other = stones.get(target)
        if other == color:
            return False
        new = replace(
            self._state,
            stones=_swapped(stones, source, target),
            dead=frozenset(_swapped_points(self._state.dead, source, target)),
            placed=frozenset(_swapped_points(self._state.placed, source, target)),
            filled=frozenset(_swapped_points(self._state.filled, source, target)),
        )
        if not self.in_seichi:
            before, after = self.territory, count_territory(self.size, new.live_stones, neutral=self.neutral)
            if after != before:
                raise TerritoryChangedError(before, after)
        self._change(new)
        return True

    def remove_dead(self) -> int:
        """Take the dead stones off the board and put them in the trays of their colors.

        The territory does not change, because dead stones are already counted as not on the board.

        Returns:
            How many stones were taken off.
        """
        removed = len(self._state.dead)
        if removed:
            self._change(_without_dead(self._state))
        return removed

    def take_off_dead(self, point: Point) -> bool:
        """Take one dead stone off the board and put it in the tray of its color.

        Returns:
            True if the point had a stone marked dead.
        """
        state = self._state
        if point not in state.dead:
            return False
        counts = state.prisoner_counts
        counts[state.stones[point]] += 1
        stones = {other: color for other, color in state.stones.items() if other != point}
        new = replace(state, stones=stones, dead=state.dead - {point}, removed=state.removed | {point})
        self._change(new.with_prisoners(counts))
        return True

    def auto_fill(self) -> FillResult:
        """Do the rest of the seichi as the computer would (one change for undo, see the module).

        The user must have taken off the dead stones and filled the dame first (ready_for_auto).
        The territory of each player stays the same as the result of the game.

        Returns:
            The areas of territory left, the prisoners that did not fit, and the steps.

        Raises:
            PlacementError: If the user has not done their part yet, or it was done ("auto_not_ready").
        """
        plan = self.plan_auto()
        self.use_auto(plan)
        return plan.result

    def plan_auto(self) -> AutoPlan:
        """Find the computer's seichi without changing the stones (it takes a few seconds; see auto_fill).

        It only reads the stones, so it can run in a background thread while nothing else changes them.

        Raises:
            PlacementError: If the user has not done their part yet, or it was done ("auto_not_ready").
        """
        if not self.ready_for_auto:
            raise PlacementError("auto_not_ready")
        confirmed = self._state.confirmed or self._confirmation()
        state = confirmed.state  # The computer starts from the confirmed end (moves after it are not used).
        steps, captured = self._steps_without_stray_stones(state)
        placed = frozenset(point for point in steps.placed if steps.stones.get(point) == steps.placed[point])
        new = replace(
            state, stones=dict(steps.stones), placed=placed, auto=True, confirmed=confirmed, marks=dict(steps.marks)
        )
        new = new.with_prisoners(steps.counts)
        owners = territory_owners(self.size, steps.stones, neutral=steps.neutral) | steps.marks
        areas = {color: sorted((len(area) for area in _areas(owners, color)), reverse=True) for color in ("B", "W")}
        result = FillResult(
            areas, dict(steps.counts), captured, dict(state.stones), steps.steps, dict(state.prisoner_counts)
        )
        return AutoPlan(self._state, new, result)

    def _steps_without_stray_stones(self, state: _State) -> tuple[_Steps, dict[str, int]]:
        """Make the steps of the computer's seichi, so that no stone is left in the other player's territory.

        The full seichi comes first (see _Steps.arrange). If it leaves a stone in the other
        player's territory (see stray_stones), the seichi is made again with fewer of its last
        parts: without making the boundary clear, then also without making the territory
        rectangles (only the prisoners are put).

        Returns:
            The steps, and how many stones of each color were captured.

        Raises:
            PlacementError: If a stone is left in the other player's territory even then
                ("seichi_auto_stray": a dead stone was not taken off).
        """
        for parts in _ARRANGE_PARTS:
            steps = _Steps(self.size, state, self.neutral)
            captured = steps.capture()
            for part in parts:
                part(steps)
            if not stray_stones(self.size, steps.stones, steps.owners()):
                return steps, captured
        raise PlacementError("seichi_auto_stray")

    def use_auto(self, plan: AutoPlan) -> bool:
        """Put the computer's seichi on the board (one change for undo).

        Returns:
            True if it was put; False if the stones changed after it was planned (it is not used then).
        """
        if self._state is not plan.before:
            return False
        self._change(plan.after)
        return True

    def place_prisoners(self, color: str, target: Point, count: int = 1) -> int:
        """Put prisoners of a color from its tray into the territory of that color at a point.

        They fill the empty area of the territory that the point belongs to, starting from the
        points nearest the edge of the board. When the area has fewer points than prisoners,
        only as many as fit are put, and the rest stay in the tray.

        Args:
            color: The color of the prisoners ("B" or "W").
            target: The point where they were dropped.
            count: How many to put (at most the number in the tray).

        Returns:
            How many were put.

        Raises:
            PlacementError: If the tray is empty, or the point is not the territory of that color.
        """
        state = self._state
        counts = state.prisoner_counts
        if counts[color] <= 0:
            raise PlacementError("prisoner_none")
        owners = territory_owners(self.size, state.live_stones, neutral=self.neutral)
        if owners.get(target) != color:
            raise PlacementError("prisoner_not_own_territory")
        points = self._fill_order(_area_of(target, owners), target)[: min(count, counts[color])]
        counts[color] -= len(points)
        stones = {**state.stones, **dict.fromkeys(points, color)}
        self._change(replace(state, stones=stones, placed=state.placed | set(points)).with_prisoners(counts))
        return len(points)

    def _fill_order(self, area: set[Point], target: Point) -> list[Point]:
        """Return the points of an area in the order to fill them: nearest the board edge first.

        Points at the same distance from the edge are taken nearest the target first, so that
        the stones go near where they were dropped.
        """
        last = self.size - 1

        def key(point: Point) -> tuple[int, int, Point]:
            """Distance from the edge, distance from the target, and the point itself (for a fixed order)."""
            x, y = point
            edge = min(x, y, last - x, last - y)
            return edge, abs(x - target[0]) + abs(y - target[1]), point

        return sorted(area, key=key)

    def take_back_prisoner(self, point: Point) -> bool:
        """Take a prisoner that was put on the board back to its tray.

        Returns:
            True if the point had a prisoner put on the board (other stones cannot go to a tray).
        """
        state = self._state
        if point not in state.placed:
            return False
        counts = state.prisoner_counts
        counts[state.stones[point]] += 1
        stones = {other: color for other, color in state.stones.items() if other != point}
        self._change(replace(state, stones=stones, placed=state.placed - {point}).with_prisoners(counts))
        return True

    def undo(self) -> bool:
        """Take back the last change. Returns True if there was one."""
        if not self._history:
            return False
        self._state = self._history.pop()
        return True

    def reset(self) -> None:
        """Go back to the final position (no dead marks or dame stones, prisoners in trays). It can be undone."""
        if self._state != self._start:
            self._change(self._start)

    def _change(self, state: _State) -> None:
        """Keep the state now for undo, and use the new one."""
        self._history.append(self._state)
        self._state = state

    def _group(self, point: Point) -> set[Point]:
        """Return the stones of the same color connected to a point."""
        stones = self._state.stones
        color = stones[point]
        group = {point}
        stack = [point]
        while stack:
            x, y = stack.pop()
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if stones.get(neighbor) == color and neighbor not in group:
                    group.add(neighbor)
                    stack.append(neighbor)
        return group

    def _on_board(self, point: Point) -> bool:
        """True if the point is on the board."""
        x, y = point
        return 0 <= x < self.size and 0 <= y < self.size


class _Steps:
    """Does the computer's seichi on a copy of the stones, and keeps each step (see Arrangement.auto_fill)."""

    def __init__(self, size: int, state: _State, neutral: frozenset[Point]):
        """Start from the stones and the prisoners now, with the points of seki that are never territory."""
        self.size = size
        self.neutral = neutral
        self.stones = dict(state.stones)
        self.counts = state.prisoner_counts
        self.placed = {point: state.stones[point] for point in state.placed}  # Prisoners on the board.
        self.steps: list[FillStep] = []
        self.marks: dict[Point, str] = {}  # The packed territory, kept as its color's (see block_tidy).

    def add(self, kind: str, color: str, points: tuple[Point, ...]) -> None:
        """Keep a step with the stones and the prisoners as they are now."""
        self.steps.append(FillStep(kind, color, points, dict(self.stones), dict(self.counts)))

    def capture(self) -> dict[str, int]:
        """Take off the groups that have no liberty (they are captured), and add them to the prisoners.

        Such groups can be left after the user's moves. A group with a prisoner the user put
        on the board is not taken (it was made by filling the territory, as in seichi).

        Returns:
            How many stones of each color were taken off.
        """
        captured = {"B": 0, "W": 0}
        for point in sorted(self.stones):
            if point not in self.stones or _liberties(self.stones, point, self.size):
                continue
            group = _group_of(self.stones, point)
            if any(stone in self.placed for stone in group):
                continue
            color = self.stones[point]
            for stone in group:
                del self.stones[stone]
            captured[color] += len(group)
            self.counts[color] += len(group)
            self.add("capture", color, tuple(sorted(group)))
        return captured

    def arrange(self) -> None:
        """Make the steps of the seichi, in the order a person does it (all three parts, see _ARRANGE_PARTS)."""
        self.put_prisoners()
        self.make_rectangles()
        self.make_boundary_clear()

    def put_prisoners(self) -> None:
        """Put the prisoners into the territory of their color (the small areas first, see auto_fill.fill_points)."""
        for color in ("B", "W"):
            territory = count_territory(self.size, self.stones, neutral=self.neutral)
            count = min(self.counts[color], territory.black if color == "B" else territory.white)
            for point in fill_points(self.size, self.stones, frozenset(), color, count, self.neutral):
                self._make(TidyMove("place", color, point, point))

    def make_rectangles(self) -> None:
        """Make each player's territory rectangles of whole tens where it is, with the player's own stones.

        See block_tidy. A packed territory may touch the other player's stones, so its points are
        marked as the player's (marks).
        """
        for color in ("B", "W"):
            other = frozenset(point for point, owner in self.marks.items() if owner != color)
            tidy = tidy_color(self.size, self.stones, color, self.neutral, other)
            for move in tidy.moves:
                self._make(move)
            if tidy.territory is not None:
                self.marks.update(dict.fromkeys(tidy.territory, color))

    def make_boundary_clear(self) -> None:
        """Swap black and white stones so that the boundary between the players is clear (see boundary)."""
        owners = territory_owners(self.size, self.stones, neutral=self.neutral) | self.marks
        for black, white in clear_boundary(self.size, self.stones, owners, self.neutral):
            self._swap(black, white)

    def owners(self) -> dict[Point, str]:
        """Return the owner of each empty point of territory now, as a person counts it (with the marks)."""
        return majority_owners(self.size, self.stones, self.neutral) | self.marks

    def _swap(self, black: Point, white: Point) -> None:
        """Swap a black stone and a white stone, and keep the step."""
        self.stones[black], self.stones[white] = "W", "B"
        placed = {point: self.placed.pop(point) for point in (black, white) if point in self.placed}
        for point, color in placed.items():
            self.placed[white if point == black else black] = color
        self.add("swap", "B", (black, white))

    def _make(self, move: TidyMove) -> None:
        """Make one step on the stones (a prisoner put, or a stone moved), and keep it."""
        source, target = move.source, move.target
        if move.kind == "place":
            self.stones[target] = self.placed[target] = move.color
            self.counts[move.color] -= 1
            self.add("place", move.color, (target,))
            return
        del self.stones[source]
        self.stones[target] = move.color
        if source in self.placed:
            self.placed[target] = self.placed.pop(source)
        self.add("move", move.color, (source, target))


# The parts of the computer's seichi that are tried, the full seichi first (see _steps_without_stray_stones).
_ARRANGE_PARTS = (
    (_Steps.put_prisoners, _Steps.make_rectangles, _Steps.make_boundary_clear),
    (_Steps.put_prisoners, _Steps.make_rectangles),
    (_Steps.put_prisoners,),
)


def _other(color: str) -> str:
    """Return the other color."""
    return "W" if color == "B" else "B"


def _group_of(stones: dict[Point, str], start: Point) -> dict[Point, str]:
    """Return the stones of the same color connected to start, as {point: color}."""
    color = stones[start]
    group, stack = {start: color}, [start]
    while stack:
        x, y = stack.pop()
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if stones.get(neighbor) == color and neighbor not in group:
                group[neighbor] = color
                stack.append(neighbor)
    return group


def _makes_atari(stones: dict[Point, str], point: Point, size: int) -> bool:
    """True if the stone on a point, or a group next to it, has one liberty or none (it could be captured)."""
    x, y = point
    starts = [point] + [p for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if p in stones]
    return any(len(_liberties(stones, start, size)) <= 1 for start in starts)


def _liberties(stones: dict[Point, str], start: Point, size: int) -> set[Point]:
    """Return the empty points next to the group of the stone on start."""
    color = stones[start]
    group, liberties, stack = {start}, set(), [start]
    while stack:
        x, y = stack.pop()
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= neighbor[0] < size and 0 <= neighbor[1] < size):
                continue
            if neighbor not in stones:
                liberties.add(neighbor)
            elif stones[neighbor] == color and neighbor not in group:
                group.add(neighbor)
                stack.append(neighbor)
    return liberties


def _without_dead(state: _State) -> _State:
    """Return the state with the dead stones taken off the board and put in the trays of their colors."""
    counts = state.prisoner_counts
    for point in state.dead:
        counts[state.stones[point]] += 1
    stones = {point: color for point, color in state.stones.items() if point not in state.dead}
    new = replace(
        state, stones=stones, dead=frozenset(), placed=state.placed - state.dead, removed=state.removed | state.dead
    )
    return new.with_prisoners(counts)


def _areas(owners: dict[Point, str], color: str) -> list[set[Point]]:
    """Return the areas (connected points) of a color's territory, from the owner of each point."""
    points = {point for point, owner in owners.items() if owner == color}
    areas = []
    while points:
        area = _area_of(points.pop(), owners)
        points -= area
        areas.append(area)
    return areas


def _same_owner_area(start: Point, owners: dict[Point, str], empty: set[Point]) -> set[Point]:
    """Return the empty points connected to start that have the same owner (or none) as start."""
    owner = owners.get(start)
    area, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if near in empty and near not in area and owners.get(near) == owner:
                area.add(near)
                stack.append(near)
    return area


def _area_of(point: Point, owners: dict[Point, str]) -> set[Point]:
    """Return the territory points of the same owner connected to a point (its empty area)."""
    color = owners[point]
    area = {point}
    stack = [point]
    while stack:
        x, y = stack.pop()
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if owners.get(neighbor) == color and neighbor not in area:
                area.add(neighbor)
                stack.append(neighbor)
    return area


def _swapped(stones: dict[Point, str], source: Point, target: Point) -> dict[Point, str]:
    """Return the stones with the stone on source moved to target (swapped with the stone there, if any)."""
    new = dict(stones)
    color = new.pop(source)
    if target in stones:
        new[source] = stones[target]
    new[target] = color
    return new


def _swapped_points(points: frozenset[Point], source: Point, target: Point) -> set[Point]:
    """Return the points with source and target exchanged (so that marks move with their stones)."""
    return {target if point == source else source if point == target else point for point in points}
