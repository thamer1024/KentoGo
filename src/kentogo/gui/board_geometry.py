"""Where the board lines, stones and labels are drawn on the screen.

This module only calculates positions, without Kivy, so that it can be tested.
Like Kivy, the screen position (0, 0) is the lower left corner, and y grows upward.
The board point (0, 0) is also the lower left corner (A1), so no flip is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[int, int]

# Space around the board, in line spacings. The left and bottom sides are wider,
# because the coordinate labels are drawn there (the same as KaTrain).
MARGIN_LOW = 1.5
MARGIN_HIGH = 0.75


@dataclass(frozen=True)
class BoardGeometry:
    """The position of a board on the screen.

    Attributes:
        size: Number of lines of the board (19 for a 19x19 board).
        origin_x: Screen x of the lower left point (A1).
        origin_y: Screen y of the lower left point (A1).
        spacing: Distance between two lines on the screen.
    """

    size: int
    origin_x: float
    origin_y: float
    spacing: float

    @classmethod
    def fit(cls, size: int, x: float, y: float, width: float, height: float, padding: float = 0.0) -> BoardGeometry:
        """Place a board in the middle of a rectangle, as large as possible.

        Space is left around the board for the coordinate labels (see MARGIN_LOW and MARGIN_HIGH).

        Args:
            size: Number of lines of the board.
            x: Screen x of the lower left corner of the rectangle.
            y: Screen y of the lower left corner of the rectangle.
            width: Width of the rectangle.
            height: Height of the rectangle.
            padding: Space between the rectangle and the board image, on every side.

        Returns:
            The position of the board.
        """
        x, y = x + padding, y + padding
        width, height = width - 2 * padding, height - 2 * padding
        side = min(width, height)
        spacing = side / (size - 1 + MARGIN_LOW + MARGIN_HIGH)
        origin_x = x + (width - side) / 2 + MARGIN_LOW * spacing
        origin_y = y + (height - side) / 2 + MARGIN_LOW * spacing
        return cls(size, origin_x, origin_y, spacing)

    def board_area(self) -> tuple[float, float, float, float]:
        """Return the area of the board image, with the margins, as (x, y, width, height)."""
        x = self.origin_x - MARGIN_LOW * self.spacing
        y = self.origin_y - MARGIN_LOW * self.spacing
        side = (self.size - 1 + MARGIN_LOW + MARGIN_HIGH) * self.spacing
        return x, y, side, side

    @property
    def stone_radius(self) -> float:
        """The radius of a stone, a little smaller than half of the spacing."""
        return self.spacing * 0.48

    def to_screen(self, point: Point) -> tuple[float, float]:
        """Return the screen position of a board point."""
        x, y = point
        return self.origin_x + x * self.spacing, self.origin_y + y * self.spacing

    def to_point(self, screen_x: float, screen_y: float) -> Point | None:
        """Return the board point nearest to a screen position.

        Args:
            screen_x: Screen x, for example of a mouse click.
            screen_y: Screen y.

        Returns:
            The point, or None if the position is more than half a spacing outside the board.
        """
        x = round((screen_x - self.origin_x) / self.spacing)
        y = round((screen_y - self.origin_y) / self.spacing)
        if 0 <= x < self.size and 0 <= y < self.size:
            return x, y
        return None


def star_points(size: int) -> list[Point]:
    """Return the star points (hoshi) of a board, in the same places as KaTrain.

    Args:
        size: Number of lines of the board.

    Returns:
        The points. Boards smaller than 7 lines have none.
    """
    if size < 7:
        return []
    edge = 2 if size <= 11 else 3
    lines = [edge, size - 1 - edge]
    if size % 2 == 1 and size > 7:
        lines.append(size // 2)
    return [(x, y) for x in lines for y in lines]
