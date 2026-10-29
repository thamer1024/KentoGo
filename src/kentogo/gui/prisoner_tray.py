"""A tray of prisoners (agehama) of one color, next to the board of the territory counting practice.

The tray shows its prisoners as stones. Ten stones are shown as one stone with
"x10" (see seichi.tray), so that a tray with many prisoners stays small. The user
drags stones out of the tray and drops them on the board: dragging the single
stones takes all of them, and dragging a "x10" takes ten. The screen decides
where they may go (see SeichiScreen).
"""

from __future__ import annotations

from collections.abc import Callable

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import StringProperty
from kivy.uix.widget import Widget

from kentogo.gui import texts, theme
from kentogo.gui.board_widget import draw_text, draw_text_from_left, is_left_click, stone_texture
from kentogo.seichi.tray import GROUP, tray_layout

STONE = 26  # dp, the size of a stone in the tray.
GAP = 4  # dp, the space between stones.
LABEL_HEIGHT = 22  # dp, the line with the name of the tray.


class PrisonerTray(Widget):
    """The prisoners of one color.

    Attributes:
        color: The color of the stones, "B" or "W".
        count: The number of prisoners in the tray.
    """

    title = StringProperty("")  # The name shown above the stones. The tray is drawn again when it changes.

    def __init__(self, color: str, drop: Callable[[str, tuple[float, float], int], None], **kwargs):
        """Make an empty tray.

        Args:
            color: The color of the stones.
            drop: Called with (color, position on the window, number of stones) when stones are
                dropped outside the tray.
            **kwargs: Kivy's widget arguments.
        """
        super().__init__(size_hint_y=None, height=dp(LABEL_HEIGHT + 2 * (STONE + GAP)), **kwargs)
        self.color = color
        self.count = 0
        self._drop = drop
        self._pointer: tuple[float, float] | None = None  # Where the dragged stones are, while dragging.
        self._picked = 0  # How many stones are dragged.
        self.bind(pos=self.redraw, size=self.redraw, title=self.redraw)

    def show(self, count: int) -> None:
        """Show a number of prisoners."""
        self.count = count
        self.redraw()

    def redraw(self, *_args) -> None:
        """Draw the name, the groups of ten (top row) and the single stones (bottom row).

        The name starts at the left, as the texts above the tray do, so that a long name is not cut off.
        """
        self.canvas.clear()
        groups, singles = tray_layout(self.count)
        size = dp(STONE)
        top = self.top - dp(LABEL_HEIGHT)
        with self.canvas:
            draw_text_from_left(
                f"{self.title}{texts.gap()}{self.count}",
                (self.x, top + dp(LABEL_HEIGHT) / 2),
                sp(14),
                theme.TEXT_COLOR,
            )
            for index in range(groups):
                x = self.x + index * (size * 2.4)
                self._draw_stone(x, top - size - dp(GAP), size)
                draw_text(f"x{GROUP}", (x + size * 1.6, top - size / 2 - dp(GAP)), sp(13), theme.TEXT_COLOR)
            for index in range(singles):
                self._draw_stone(self.x + index * (size + dp(GAP)), self.y, size)
        self._draw_pointer()

    def stone_center(self) -> tuple[float, float]:
        """Return the center of the first single stone (in the coordinates of the tray's parent)."""
        size = dp(STONE)
        return self.x + size / 2, self.y + size / 2

    def on_touch_down(self, touch) -> bool:
        """Pick up all single stones (bottom row), or a group of ten (top row)."""
        if not self.collide_point(*touch.pos) or not is_left_click(touch) or self.count == 0 or self.disabled:
            return super().on_touch_down(touch)
        groups, singles = tray_layout(self.count)
        if touch.y <= self.y + dp(STONE):
            self._picked = singles
        elif touch.y <= self.top - dp(LABEL_HEIGHT) and groups > 0:
            self._picked = GROUP
        else:
            return True  # The name of the tray: nothing to pick up.
        self._pointer = touch.pos
        touch.grab(self)
        self._draw_pointer()
        return True

    def on_touch_move(self, touch) -> bool:
        """Move the picked stone with the pointer."""
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        self._pointer = touch.pos
        self._draw_pointer()
        return True

    def on_touch_up(self, touch) -> bool:
        """Drop the picked stone: outside the tray, the screen decides what happens."""
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        self._pointer = None
        self._draw_pointer()
        if not self.collide_point(*touch.pos):
            self._drop(self.color, touch.pos, self._picked)
        return True

    def _draw_stone(self, x: float, y: float, size: float) -> None:
        """Draw one stone with its lower left corner at (x, y)."""
        Color(1, 1, 1, 1)
        Rectangle(pos=(x, y), size=(size, size), texture=stone_texture(self.color))

    def _draw_pointer(self) -> None:
        """Draw the dragged stones where the pointer is, with their number (on top of everything of this tray)."""
        self.canvas.after.clear()
        if self._pointer is None:
            return
        size = dp(STONE)
        x, y = self._pointer
        with self.canvas.after:
            Color(1, 1, 1, 0.85)
            Rectangle(pos=(x - size / 2, y - size / 2), size=(size, size), texture=stone_texture(self.color))
            if self._picked > 1:
                draw_text(f"x{self._picked}", (x + size * 1.1, y), sp(14), theme.TEXT_COLOR)
