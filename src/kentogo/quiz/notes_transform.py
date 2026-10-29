"""Change the words in the notes so that they match a rotated, flipped or color-swapped board.

When a problem is shown changed (see transform.BoardTransform), the notes still
describe the original board. This module rewrites these words in the notes:

- Points in GTP coordinates, such as "D17" or "G5〜K5", also with the color first as KaTrain
  writes them, such as "BJ11" (black on J11).
- The color words 黒 and 白 (and Black and White), when colors are swapped.
- Directions on the board in Japanese and English, such as 左上, 右辺,
  "upper right" or "left side".

Other words are kept as they are. For example "5の段" (the fifth line from the
bottom) cannot be rewritten simply, and stays the same. All words are rewritten
in one pass, so a word that has been rewritten is not rewritten again.
"""

from __future__ import annotations

import re

from kentogo.common.types import GTP_COLUMNS
from kentogo.quiz.transform import BoardTransform

# A direction is a point on a 3x3 board: x is 0 (left) to 2 (right), and y is
# 0 (bottom) to 2 (top), the same as the coordinates of the board.
# Each family keeps its own words, so that "upper right" becomes "lower left",
# and "top right" becomes "bottom left".
DIRECTION_FAMILIES: tuple[dict[tuple[int, int], str], ...] = (
    {(0, 2): "左上", (2, 2): "右上", (0, 0): "左下", (2, 0): "右下"},
    {(1, 2): "上辺", (1, 0): "下辺", (0, 1): "左辺", (2, 1): "右辺"},
    {(1, 2): "上側", (1, 0): "下側", (0, 1): "左側", (2, 1): "右側"},
    {(0, 2): "upper left", (2, 2): "upper right", (0, 0): "lower left", (2, 0): "lower right"},
    {(0, 2): "top left", (2, 2): "top right", (0, 0): "bottom left", (2, 0): "bottom right"},
    {(1, 2): "top side", (1, 0): "bottom side", (0, 1): "left side", (2, 1): "right side"},
)

COLOR_WORDS = {"黒": "白", "白": "黒", "Black": "White", "White": "Black", "black": "white", "white": "black"}

# Where each direction word comes from: word -> (family, point).
_DIRECTIONS = {word: (family, point) for family in DIRECTION_FAMILIES for point, word in family.items()}

# A GTP point that is not part of a longer word or number, such as "D17" in "黒D17の", maybe with
# the color first ("BJ11"). "B4" alone is the point B4, as no point follows its "B".
_POINT = r"(?<![A-Za-z0-9])[BW]?[A-HJ-Z][1-9][0-9]?(?![A-Za-z0-9])"


def _pattern() -> re.Pattern:
    """Make one regular expression that finds every word that may be rewritten.

    Longer words come first, so that "upper right" is found before "right".
    English words must be whole words.
    """
    words = sorted([*_DIRECTIONS, *COLOR_WORDS], key=len, reverse=True)
    parts = [rf"\b{re.escape(word)}\b" if word.isascii() else re.escape(word) for word in words]
    return re.compile("|".join([_POINT, *parts]))


_PATTERN = _pattern()


def transform_notes(notes: str, transform: BoardTransform, size: int) -> str:
    """Rewrite the points, colors and directions in notes for a changed board.

    Args:
        notes: The notes, written for the original board.
        transform: How the board is changed.
        size: The size of the board.

    Returns:
        The notes for the changed board. They are the same if the transform changes nothing.
    """
    if transform == BoardTransform():
        return notes
    return _PATTERN.sub(lambda match: _rewrite(match.group(0), transform, size), notes)


def _rewrite(word: str, transform: BoardTransform, size: int) -> str:
    """Rewrite one word that the pattern found. Words that do not fit the board stay the same."""
    if word in COLOR_WORDS:
        return COLOR_WORDS[word] if transform.swap_colors else word
    elif word in _DIRECTIONS:
        family, point = _DIRECTIONS[word]
        return family[transform.point(point, 3)]
    color, point = ("", word) if word[1].isdigit() else (word[0], word[1:])
    column, row = GTP_COLUMNS.index(point[0]), int(point[1:])
    if column >= size or row > size:
        return word
    x, y = transform.point((column, row - 1), size)
    if color and transform.swap_colors:
        color = {"B": "W", "W": "B"}[color]
    return f"{color}{GTP_COLUMNS[x]}{y + 1}"
