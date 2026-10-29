"""A board where the user arranges the stones for the territory counting practice (seichi).

Clicking a stone (pressing and releasing on the same point) marks its group as
dead, or alive again. Clicking an open dame fills it with a stone, and clicking
that stone takes it back. A dead stone dragged off the board goes to its tray.
The territory is shown with a small square of the owner's color on each point. The user drags a stone with the left mouse button (or a
finger) and drops it on another point. On an empty point the stone moves there;
on a stone of the other color the two stones are swapped. The stone follows the pointer while it is
dragged. The stones are kept in a seichi.arrangement.Arrangement.
A move that would change the territory of a player is not made: the stone goes
back, and the screen is told (when_refused) so that it can warn the user.
Prisoners come from the trays (drop_prisoners). A prisoner put on the board and
dropped outside the board goes back to its tray.

The board can also show a step of the computer's seichi (show_step). While it does,
the stones cannot be moved; end_steps shows the stones as they are now again.
animate_step shows a step with its stones sliding to their points, as if a person moved
them (see gui.step_motion).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle

from kentogo.common.types import Position
from kentogo.gui import theme
from kentogo.gui.board_view import MARK_ACTUAL, MARK_ANSWER, BoardView
from kentogo.gui.board_widget import BoardWidget, is_left_click, stone_texture
from kentogo.gui.step_motion import StoneMotion, between, without_moving
from kentogo.seichi.arrangement import Arrangement, AutoPlan, PlacementError, TerritoryChangedError
from kentogo.seichi.territory import territory_owners

Point = tuple[int, int]

FRAME_SECONDS = 1 / 60  # How often a moving stone is drawn again.


class EditableBoard(BoardWidget):
    """A board whose stones can be dragged to other points, and swapped.

    Attributes:
        arrangement: The stones and the history of the changes.
        when_changed: Called after the stones have changed (or None).
        when_refused: Called with the TerritoryChangedError of a refused move (or None).
        when_not_allowed: Called with a key of the screen texts when a click is not allowed,
            for example a dame that would put a group in atari (or None).
    """

    def __init__(
        self,
        position: Position,
        when_changed: Callable[[], None] | None = None,
        when_refused: Callable[[TerritoryChangedError], None] | None = None,
        **kwargs,
    ):
        """Make the board with the stones of a position.

        Args:
            position: The final position of the game.
            when_changed: Called after the stones have changed.
            when_refused: Called when a move is refused because it would change the territory.
            **kwargs: Kivy's widget arguments.
        """
        super().__init__(**kwargs)
        self.arrangement = Arrangement(position)
        self.when_changed = when_changed
        self.when_refused = when_refused
        self.when_not_allowed: Callable[[str], None] | None = None
        self._dragged: Point | None = None  # The point of the stone being dragged.
        self._clicked_empty: Point | None = None  # An empty point pressed (a click fills it as dame).
        self._pointer: tuple[float, float] = (0.0, 0.0)  # Where the dragged stone is drawn.
        self._step: BoardView | None = None  # A step of the computer's seichi being shown.
        # While stones of a step are moving: the timer, and what is called when they are put.
        self._animation: tuple[object, Callable[[], None]] | None = None
        self.refresh()

    def show_step(self, stones: dict[Point, str], points: tuple[Point, ...]) -> None:
        """Show the stones of a step of the computer's seichi, with marks on the points of the step.

        A step with two points (from, to) gets a triangle where the stone was and a circle where a
        stone is put, as the step's words say (see texts.fill_step_text). Other points get a circle.
        """
        if len(points) == 2:
            marks = {points[0]: (MARK_ACTUAL,), points[1]: (MARK_ANSWER,)}
        else:
            marks = {point: (MARK_ANSWER,) for point in points}
        self._dragged = None
        self._step = BoardView(
            self.arrangement.size,
            stones,
            marks=marks,
            territory=territory_owners(self.arrangement.size, stones, neutral=self.arrangement.neutral),
        )
        self.show(self._step)

    def animate_step(
        self,
        stones: dict[Point, str],
        points: tuple[Point, ...],
        motions: tuple[StoneMotion, ...],
        seconds: float,
        tray_position: Callable[[str], tuple[float, float]],
        on_done: Callable[[], None],
    ) -> None:
        """Show a step with its stones sliding to their points, then call on_done (which shows the step).

        Args:
            stones: The stones after the step.
            points: The points of the step (for the marks).
            motions: The stones that move (see step_motion.step_motions).
            seconds: How long the move takes. With 0, or no stone to move, on_done is called at once.
            tray_position: Returns where the tray of prisoners of a color is, in window coordinates.
            on_done: Called when the stones are put (also when finish_animation ends the move early).
        """
        self.cancel_animation()
        if not motions or seconds <= 0 or self.view is None:
            on_done()
            return
        self.show_step(without_moving(stones, motions), points)
        geometry = self._geometry()
        paths = [(m.color, self._start_of(m, geometry, tray_position), geometry.to_screen(m.target)) for m in motions]
        started = time.monotonic()

        def tick(_dt: float) -> bool | None:
            """Draw the moving stones where they are now, and put them when the time is over."""
            fraction = (time.monotonic() - started) / seconds
            if fraction >= 1:
                self.finish_animation()
                return False
            self._draw_moving_stones([(color, between(start, end, fraction)) for color, start, end in paths])
            return None

        self._animation = (Clock.schedule_interval(tick, FRAME_SECONDS), on_done)
        tick(0)

    def finish_animation(self) -> None:
        """Put the moving stones at once (if any are moving), and call on_done of animate_step."""
        if self._animation is None:
            return
        on_done = self._animation[1]
        self.cancel_animation()
        on_done()

    def cancel_animation(self) -> None:
        """Stop the moving stones without calling on_done (the screen shows something else)."""
        if self._animation is not None:
            self._animation[0].cancel()
            self._animation = None
            self.canvas.after.clear()

    def _start_of(
        self, motion: StoneMotion, geometry, tray_position: Callable[[str], tuple[float, float]]
    ) -> tuple[float, float]:
        """Return where a moving stone starts: its point, or its tray (changed into this board's coordinates)."""
        if motion.source is not None:
            return geometry.to_screen(motion.source)
        return self.to_widget(*tray_position(motion.color))

    def _draw_moving_stones(self, stones: list[tuple[str, tuple[float, float]]]) -> None:
        """Draw stones that are moving (above the board), a little transparent like a dragged stone."""
        self.canvas.after.clear()
        half = self._geometry().spacing * theme.STONE_SIZE
        with self.canvas.after:
            for color, (x, y) in stones:
                Color(1, 1, 1, 0.85)
                Rectangle(pos=(x - half, y - half), size=(half * 2, half * 2), texture=stone_texture(color))

    def end_steps(self) -> None:
        """Stop showing a step, and show the stones as they are now (they can be moved again)."""
        self.cancel_animation()
        self._step = None
        self.refresh()

    def refresh(self) -> None:
        """Show the stones as they are now (without the stone being dragged)."""
        if self._step is not None:
            return
        stones = self.arrangement.stones
        if self._dragged is not None:
            stones.pop(self._dragged, None)
        arrangement = self.arrangement
        dead = arrangement.dead & stones.keys()  # The dragged stone is not drawn on the board.
        self.show(
            BoardView(
                arrangement.size,
                stones,
                dead=frozenset(dead),
                territory=arrangement.territory_points,
            )
        )

    def remove_dead(self) -> None:
        """Take the dead stones off the board and put them in the trays."""
        if self.arrangement.remove_dead():
            self._changed()

    def use_auto(self, plan: AutoPlan) -> bool:
        """Put the computer's seichi on the board (see Arrangement.use_auto). Returns True if it was put."""
        used = self.arrangement.use_auto(plan)
        self._changed()
        return used

    def drop_prisoners(self, color: str, position: tuple[float, float], count: int) -> int:
        """Put prisoners from a tray into the territory at a window position (see Arrangement.place_prisoners).

        Returns:
            How many were put (0 outside the board).

        Raises:
            seichi.arrangement.PlacementError: If it may not go there (the message is a key of the
                screen texts).
        """
        if self.view is None or not self.collide_point(*position):
            return 0
        point = self._geometry().to_point(*position)
        if point is None:
            return 0
        placed = self.arrangement.place_prisoners(color, point, count)
        self._changed()
        return placed

    def undo(self) -> None:
        """Take back the last change."""
        if self.arrangement.undo():
            self._changed()

    def reset(self) -> None:
        """Go back to the final position."""
        self.arrangement.reset()
        self._changed()

    def on_touch_down(self, touch) -> bool:
        """Pick up the stone under the pointer."""
        if self._step is not None or self.disabled:
            return False  # A step of the computer's seichi is shown, or the computer is thinking.
        if self.view is None or not self.collide_point(*touch.pos) or not is_left_click(touch):
            return super().on_touch_down(touch)
        point = self._geometry().to_point(*touch.pos)
        if point is None:
            return True
        if point not in self.arrangement.stones:
            self._clicked_empty = point  # Filled as dame when released here.
            touch.grab(self)
            return True
        self._dragged = point
        self._pointer = touch.pos
        touch.grab(self)
        self.refresh()
        return True

    def on_touch_move(self, touch) -> bool:
        """Move the picked stone with the pointer."""
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        self._pointer = touch.pos
        self._draw_dragged()
        return True

    def on_touch_up(self, touch) -> bool:
        """Put the picked stone on the point under the pointer (or back, outside the board).

        Released on the same point, it was a click (see _click). Dropped outside the board, a prisoner
        goes back to its tray and a dead stone is taken off.
        """
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        source, self._dragged = self._dragged, None
        target = self._geometry().to_point(*touch.pos)
        empty, self._clicked_empty = self._clicked_empty, None
        if empty is not None or (source is not None and target == source):
            if target in (empty, source):
                self._click(target)
            else:
                self.refresh()
            return True
        if source is not None and target is None:
            arrangement = self.arrangement
            if arrangement.take_back_prisoner(source) or arrangement.take_off_dead(source):
                self._changed()
            else:
                self.refresh()
            return True
        self._move(source, target)
        return True

    def _click(self, point: Point) -> None:
        """A click: fill an open dame, take back a dame stone, or mark a group dead (or alive again).

        In the seichi phase (after the end is confirmed), a click on an empty point sets who owns
        it (see Arrangement.mark_area), and a click on a stone does nothing.
        """
        arrangement = self.arrangement
        try:
            if arrangement.in_seichi:
                if point in arrangement.stones:
                    self.refresh()
                    return
                arrangement.mark_area(point)
            elif point not in arrangement.stones:
                arrangement.fill_dame(point)
            elif not arrangement.remove_dame(point):
                arrangement.toggle_dead(point)
        except PlacementError as refused:
            self.refresh()
            if self.when_not_allowed is not None:
                self.when_not_allowed(str(refused))
            return
        self._changed()

    def _move(self, source: Point | None, target: Point | None) -> None:
        """Move a stone, or put it back when the move is not allowed."""
        try:
            moved = source is not None and target is not None and self.arrangement.move(source, target)
        except TerritoryChangedError as refused:
            self.refresh()  # The stone goes back to where it was.
            if self.when_refused is not None:
                self.when_refused(refused)
            return
        if moved:
            self._changed()
        else:
            self.refresh()

    def redraw(self, *args) -> None:
        """Draw the board, and the stone being dragged on top of it (moving stones are drawn by their timer)."""
        super().redraw(*args)
        if self._animation is None:
            self._draw_dragged()

    def _draw_dragged(self) -> None:
        """Draw the dragged stone where the pointer is (a little transparent, so the point below shows)."""
        self.canvas.after.clear()
        if self._dragged is None or self.view is None:
            return
        color = self.arrangement.stones[self._dragged]
        half = self._geometry().spacing * theme.STONE_SIZE
        x, y = self._pointer
        with self.canvas.after:
            Color(1, 1, 1, 0.85)
            Rectangle(pos=(x - half, y - half), size=(half * 2, half * 2), texture=stone_texture(color))

    def _changed(self) -> None:
        """Show the new stones, and tell the screen."""
        self.refresh()
        if self.when_changed is not None:
            self.when_changed()
