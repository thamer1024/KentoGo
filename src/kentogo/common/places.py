"""The names of the places on the board: the region of a point (such as the top right corner) and its line.

The board is cut in three in each direction: on 19x19, columns A to F are the left, G to N the middle
and O to T the right; rows 1 to 6 are the bottom, 7 to 13 the middle and 14 to 19 the top. A point
in the left or right part and in the top or bottom part is in a corner region, and in the corner itself
(such as 左上隅) when it is on the fourth line or lower in both directions. A point in only one of them is
on a side, and one in neither is in the center. The same rules as the user's own prototype (kento_prompt).

The regions are names for the screens and the prompts to translate (such as "top_right_corner").
"""

from __future__ import annotations

Point = tuple[int, int]
CORNER_LINE = 4  # A point on this line or lower in both directions of a corner region is in the corner.
CENTER = "center"


def line_of(point: Point, size: int) -> int:
    """Return the line of a point from the nearest edge (the first line is 1)."""
    x, y = point
    return min(x, size - 1 - x, y, size - 1 - y) + 1


def region_of(point: Point, size: int) -> str:
    """Return the region of a point.

    Returns:
        "top_left_corner" (the corner itself), "top_left" (the corner region), "left_side", "top_side",
        ..., or "center". The first word is top or bottom, the second left or right.
    """
    x, y = point
    third = size // 3
    across = "left" if x < third else "right" if x >= size - third else ""
    upward = "bottom" if y < third else "top" if y >= size - third else ""
    if across and upward:
        in_corner = min(x, size - 1 - x) < CORNER_LINE and min(y, size - 1 - y) < CORNER_LINE
        return f"{upward}_{across}_corner" if in_corner else f"{upward}_{across}"
    if across or upward:
        return f"{across or upward}_side"
    return CENTER
