"""The board on the screen: it draws a BoardView and reports clicked points.

The board and stone images and the colors are the same as KaTrain's (see gui.theme).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.widget import Widget

from kentogo.common.types import GTP_COLUMNS
from kentogo.gui import theme
from kentogo.gui.board_geometry import BoardGeometry, star_points
from kentogo.gui.board_view import MARK_ACTUAL, MARK_ANSWER, MARK_BEST, MARK_COMPARE, BoardView, mark_outline

# The mark of territory in the territory counting practice: a square in the owner's color
# (its size as a part of the spacing).
TERRITORY_SQUARE = 0.36
TERRITORY_COLORS = {"B": (0.08, 0.08, 0.08, 0.9), "W": (0.97, 0.97, 0.97, 0.95)}

# KataGo's territory (see BoardView.ownership): the largest square (as a part of the spacing),
# the smallest owner shown, and how sure the other player must be to show a stone as dead.
OWNERSHIP_SQUARE = 0.5
OWNERSHIP_LEAST = 0.15
OWNERSHIP_DEAD = 0.5
OWNERSHIP_COLORS = {"B": (0.08, 0.08, 0.08, 0.75), "W": (0.97, 0.97, 0.97, 0.8)}

# How much a stone marked dead is shown (1 is a normal stone).
DEAD_STONE_ALPHA = 0.45

# Space around the board image, on every side.
BOARD_PADDING_DP = 16

# Colors of the marks, as (red, green, blue, alpha).
MARK_COLORS = {
    MARK_ANSWER: (0.1, 0.35, 0.95, 1),
    MARK_ACTUAL: (0.9, 0.1, 0.1, 1),
    MARK_BEST: (0.05, 0.65, 0.2, 1),
    MARK_COMPARE: (0.72, 0.15, 0.85, 1),  # Purple: not like the other marks, and easy to see on the board.
}


class BoardWidget(Widget):
    """A widget that draws a board.

    Call show() to change what is drawn. When the user clicks a point on the board,
    the event on_point is sent with the point (x, y) as its argument.
    """

    __events__ = ("on_point",)

    def __init__(self, **kwargs):
        """Make an empty board widget. Kivy's widget arguments are passed through."""
        super().__init__(**kwargs)
        self.view: BoardView | None = None
        self.bind(pos=self.redraw, size=self.redraw)

    def show(self, view: BoardView | None) -> None:
        """Draw a new view, or nothing if view is None."""
        self.view = view
        self.redraw()

    def on_point(self, point: tuple[int, int]) -> None:
        """Default handler of the on_point event. It does nothing."""

    def on_touch_down(self, touch) -> bool:
        """Send on_point when the user clicks a point of the board with the left button.

        Kivy also sends scrolling (mouse wheel or two fingers on a trackpad) and the
        right button as touches, so only a left click (or a real touch) is an answer.
        """
        if self.view is None or not self.collide_point(*touch.pos) or not is_left_click(touch):
            return super().on_touch_down(touch)
        point = self._geometry().to_point(*touch.pos)
        if point is None:
            return super().on_touch_down(touch)
        self.dispatch("on_point", point)
        return True

    def redraw(self, *args) -> None:
        """Draw the board again (called when the view, size or position changes)."""
        self.canvas.clear()
        if self.view is None:
            return
        geometry = self._geometry()
        with self.canvas:
            Color(*theme.BACKGROUND_COLOR)
            Rectangle(pos=self.pos, size=self.size)
            x, y, width, height = geometry.board_area()
            Color(*theme.BOARD_TINT)
            Rectangle(pos=(x, y), size=(width, height), texture=_texture(theme.BOARD_IMAGE))
            self._draw_grid(geometry)
            self._draw_coordinates(geometry)
            self._draw_territory(geometry)
            self._draw_stones(geometry)
            self._draw_ownership(geometry)
            self._draw_marks(geometry)

    def _geometry(self) -> BoardGeometry:
        """Return the position of the board inside this widget."""
        return BoardGeometry.fit(self.view.size, self.x, self.y, self.width, self.height, dp(BOARD_PADDING_DP))

    def _draw_grid(self, geometry: BoardGeometry) -> None:
        """Draw the lines and the star points."""
        last = geometry.size - 1
        Color(*theme.LINE_COLOR)
        for i in range(geometry.size):
            Line(points=[*geometry.to_screen((i, 0)), *geometry.to_screen((i, last))], width=1)
            Line(points=[*geometry.to_screen((0, i)), *geometry.to_screen((last, i))], width=1)
        radius = geometry.spacing * 0.1
        for point in star_points(geometry.size):
            x, y = geometry.to_screen(point)
            Ellipse(pos=(x - radius, y - radius), size=(radius * 2, radius * 2))

    def _draw_coordinates(self, geometry: BoardGeometry) -> None:
        """Draw the column letters below the board and the row numbers left of it."""
        font_size = geometry.spacing * 0.45
        for i in range(geometry.size):
            x, y = geometry.to_screen((i, 0))
            draw_text(GTP_COLUMNS[i], (x, y - geometry.spacing * 0.9), font_size, theme.LINE_COLOR)
            x, y = geometry.to_screen((0, i))
            draw_text(str(i + 1), (x - geometry.spacing * 0.9, y), font_size, theme.LINE_COLOR)

    def _draw_territory(self, geometry: BoardGeometry) -> None:
        """Draw a small square of the owner's color on each point of territory."""
        half = geometry.spacing * TERRITORY_SQUARE / 2
        for point, color in self.view.territory.items():
            x, y = geometry.to_screen(point)
            Color(*TERRITORY_COLORS[color])
            Rectangle(pos=(x - half, y - half), size=(half * 2, half * 2))

    def _draw_ownership(self, geometry: BoardGeometry) -> None:
        """Draw KataGo's territory: a square of the owner's color, larger the surer it is (see BoardView.ownership)."""
        for point, value in self.view.ownership.items():
            owner = "B" if value > 0 else "W"
            stone = self.view.stones.get(point)
            if abs(value) < OWNERSHIP_LEAST or stone == owner or (stone is not None and abs(value) < OWNERSHIP_DEAD):
                continue
            half = geometry.spacing * OWNERSHIP_SQUARE * min(abs(value), 1.0) / 2
            x, y = geometry.to_screen(point)
            Color(*OWNERSHIP_COLORS[owner])
            Rectangle(pos=(x - half, y - half), size=(half * 2, half * 2))

    def _draw_stones(self, geometry: BoardGeometry) -> None:
        """Draw the stones, the numbers on them, and the mark of the last move."""
        half = geometry.spacing * theme.STONE_SIZE
        for point, color in self.view.stones.items():
            x, y = geometry.to_screen(point)
            dead = point in self.view.dead
            Color(1, 1, 1, DEAD_STONE_ALPHA if dead else 1)
            Rectangle(pos=(x - half, y - half), size=(half * 2, half * 2), texture=_texture(theme.STONE_IMAGES[color]))
            if dead:
                # A cross as well as the fading, so that dead stones are seen without telling shades apart.
                arm = geometry.stone_radius * 0.45
                Color(*theme.NUMBER_COLORS[color])
                Line(points=[x - arm, y - arm, x + arm, y + arm], width=2)
                Line(points=[x - arm, y + arm, x + arm, y - arm], width=2)
            number = self.view.numbers.get(point)
            if number is not None:
                draw_text(str(number), (x, y), geometry.spacing * 0.5, theme.NUMBER_COLORS[color])
        last = self.view.last_move
        if last is not None and last in self.view.stones and last not in self.view.numbers:
            x, y = geometry.to_screen(last)
            Color(*theme.LAST_MOVE_COLOR)
            dot = geometry.stone_radius * 0.35
            Ellipse(pos=(x - dot, y - dot), size=(dot * 2, dot * 2))

    def _draw_marks(self, geometry: BoardGeometry) -> None:
        """Draw a colored mark on each marked point (a ring, or a shape for each kind).

        Several marks on one point are drawn inside each other.
        """
        for point, kinds in self.view.marks.items():
            center = geometry.to_screen(point)
            for index, kind in enumerate(kinds):
                Color(*MARK_COLORS[kind])
                radius = geometry.stone_radius * (0.75 - 0.2 * index)
                corners = mark_outline(kind, center, radius)
                if corners is None:
                    Line(circle=(*center, radius), width=2)
                else:
                    Line(points=corners, close=True, width=2)


def is_left_click(touch) -> bool:
    """Return True for a left mouse click or a touch on a touch screen.

    A touch from a mouse has a "button": "left", "right", "middle", or "scrollup",
    "scrolldown", "scrollleft", "scrollright" for scrolling. Other touches have no button.
    """
    if "button" not in touch.profile:
        return True
    return touch.button == "left"


@cache
def stone_texture(color: str) -> Texture:
    """Return the texture of a stone of a color ("B" or "W"), the same image as on the board."""
    return _texture(theme.STONE_IMAGES[color])


def _texture(path: Path) -> Texture:
    """Load an image once, and return its texture."""
    return CoreImage(str(path)).texture


def draw_text_from_left(text: str, left: tuple[float, float], font_size: float, color: tuple) -> None:
    """Draw a short text that starts at the given screen position (its left end, at the middle of its height)."""
    label = CoreLabel(text=text, font_size=font_size)
    label.refresh()
    texture = label.texture
    Color(*color)
    x, y = left
    Rectangle(texture=texture, pos=(x, y - texture.height / 2), size=texture.size)


def draw_text(text: str, center: tuple[float, float], font_size: float, color: tuple) -> None:
    """Draw a short text with its center at the given screen position."""
    label = CoreLabel(text=text, font_size=font_size)
    label.refresh()
    texture = label.texture
    Color(*color)
    x, y = center
    Rectangle(texture=texture, pos=(x - texture.width / 2, y - texture.height / 2), size=texture.size)
