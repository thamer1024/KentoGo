"""A check box drawn in the same way as KaTrain's.

Kivy's own check box is a small gray image that is hard to see on the dark
background. KaTrain draws its check boxes with lines instead, in the style of
Material Design: a square with round corners, and a tick when it is checked.
This check box copies that shape, its sizes and its colors (see
katrain/gui/widgets/material/checkbox.py). KaTrain's small animation and
ripple when it is clicked are left out.

The class must not be named "CheckBox": Kivy applies the style rules of a class
by its name, and would then try to draw Kivy's own check box images too.
"""

from __future__ import annotations

from kivy.graphics import Color, SmoothLine
from kivy.metrics import sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.widget import Widget

from kentogo.gui import theme


class MaterialCheckBox(ToggleButtonBehavior, Widget):
    """A check box. Clicking it turns it on or off.

    Attributes:
        active: True when the box is checked.
        box_size: The size of the square. It is drawn in the middle of the widget.
    """

    active = BooleanProperty(False)
    box_size = NumericProperty(sp(16))

    def __init__(self, **kwargs):
        """Make the check box and draw it.

        Args:
            **kwargs: Kivy's widget arguments, such as size and active.
        """
        super().__init__(**kwargs)
        with self.canvas:
            self._box_color = Color()
            self._box = SmoothLine()
            self._tick_color = Color()
            self._tick = SmoothLine(cap="round", joint="round")
        self.bind(pos=self._draw, size=self._draw, active=self._draw, disabled=self._draw, box_size=self._draw)
        self._draw()

    def on_state(self, _widget, state: str) -> None:
        """Keep active the same as the state of the toggle button ("down" means checked)."""
        self.active = state == "down"

    def on_active(self, _widget, active: bool) -> None:
        """Keep the state of the toggle button the same as active, when active is set by the program."""
        self.state = "down" if active else "normal"

    def _draw(self, *_args) -> None:
        """Draw the square and the tick, in the color for the current state."""
        if self.disabled:
            color = theme.CHECKBOX_DISABLED_COLOR
        elif self.active:
            color = theme.CHECKBOX_SELECTED_COLOR
        else:
            color = theme.CHECKBOX_UNSELECTED_COLOR
        size = self.box_size
        x, y = self.center_x, self.center_y
        line_width = max(0.01, size / 21)
        self._box_color.rgba = color
        self._box.rounded_rectangle = (x - size / 2, y - size / 2, size, size, size / 9)
        self._box.width = line_width
        self._tick_color.rgba = color if self.active else (0, 0, 0, 0)
        self._tick.points = (
            x - size * 0.28, y + size * 0.02,
            x - size * 0.08, y - size * 0.20,
            x + size * 0.30, y + size * 0.22,
        )  # fmt: skip
        self._tick.width = line_width
