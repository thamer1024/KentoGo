"""Make the icon of the KentoGo program (KentoGo.exe and KentoGo.app).

The icon is a small Go board on a rounded square. A wall of black and white stones goes
down the middle, stepping left and right, and splits the board into black's territory (left,
with small black squares) and white's territory (right, with small white squares), as the
territory counting practice does.

Small icons (Windows uses them in lists and on the task bar) are drawn with fewer lines and
without the squares, so that they stay clear (see SMALL).

It writes kentogo.png (1024 pixels), kentogo.ico (Windows) and kentogo.icns (macOS) into the
output folder, and, if asked, the icon of the window (WINDOW_ICON_SIZE pixels, see
gui/theme.APP_ICON), which Kivy shows on the window, the task bar and the Dock.

Usage:
    python tools/make_icon.py OUTPUT_DIR [--window-icon PNG]

Example:
    python tools/make_icon.py packaging/icons --window-icon src/kentogo/images/app_icon.png

Needs Pillow (not a dependency of KentoGo itself).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SUPERSAMPLE = 4  # Drawn larger and made smaller, for smooth edges.
BOARD_TOP = (238, 200, 124)
BOARD_BOTTOM = (212, 160, 84)
LINE_COLOR = (96, 64, 30)
BLACK = (26, 26, 30)
WHITE = (247, 247, 243)
WHITE_EDGE = (176, 176, 170)


@dataclass(frozen=True)
class Style:
    """How an icon is drawn. Lengths are parts of the size of the icon.

    Attributes:
        lines: The board has lines x lines points.
        wall: The column (0 at the left) of the black stone of the wall on each row; the white
            stone is just right of it.
        margin: The space around the rounded square (macOS icons leave this space).
        radius: The corner of the rounded square.
        line_width: The width of the lines.
        marks: True to mark the territory with small squares.
    """

    lines: int
    wall: tuple[int, ...]
    margin: float
    radius: float
    line_width: float
    marks: bool


LARGE = Style(7, (2, 3, 3, 2, 3, 2, 2), margin=0.098, radius=0.18, line_width=0.006, marks=True)
SMALL = Style(5, (1, 2, 1, 2, 1), margin=0.03, radius=0.16, line_width=0.03, marks=False)
LARGE_SIZE = 1024
SMALL_SIZES = (16, 24, 32, 48)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
WINDOW_ICON_SIZE = 256


def draw_icon(size: int, style: Style) -> Image.Image:
    """Draw the icon at a size (pixels) in a style."""
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    _draw_board(image, style)
    first, step = _grid(big, style)
    draw = ImageDraw.Draw(image)
    for row, column in enumerate(style.wall):
        for col in range(style.lines):
            center = (first + col * step, first + row * step)
            if col == column:
                _draw_stone(image, center, step, BLACK)
            elif col == column + 1:
                _draw_stone(image, center, step, WHITE)
            elif style.marks:
                _draw_mark(draw, center, step, BLACK if col < column else WHITE)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _grid(size: int, style: Style) -> tuple[float, float]:
    """Return where the first line is, and the space between the lines (in drawing pixels)."""
    inner = size * (1 - 2 * style.margin)
    step = inner / (style.lines + 0.8)
    return size * style.margin + step * 0.9, step


def _draw_board(image: Image.Image, style: Style) -> None:
    """Draw the shadow, the rounded square of wood (lighter at the top) and the lines."""
    size = image.width
    edge = size * style.margin
    box = (edge, edge, size - edge, size - edge)
    radius = size * style.radius
    if style.margin > 0.05:
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        drop = size * 0.012
        ImageDraw.Draw(shadow).rounded_rectangle(
            (box[0], box[1] + drop, box[2], box[3] + drop), radius, fill=(0, 0, 0, 80)
        )
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(size * 0.016)))
    wood = Image.new("RGBA", image.size)
    wood_draw = ImageDraw.Draw(wood)
    for y in range(size):
        t = y / size
        color = tuple(round(a + (b - a) * t) for a, b in zip(BOARD_TOP, BOARD_BOTTOM, strict=True))
        wood_draw.line((0, y, size, y), fill=(*color, 255))
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    image.paste(wood, (0, 0), mask)
    draw = ImageDraw.Draw(image)
    first, step = _grid(size, style)
    last = first + (style.lines - 1) * step
    width = max(1, round(size * style.line_width))
    for index in range(style.lines):
        position = first + index * step
        draw.line((first, position, last, position), fill=LINE_COLOR, width=width)
        draw.line((position, first, position, last), fill=LINE_COLOR, width=width)


def _draw_stone(image: Image.Image, center: tuple[float, float], step: float, color: tuple) -> None:
    """Draw a stone with a soft shadow. A black stone also has a soft light at its upper left; a white one is plain."""
    x, y = center
    radius = step * 0.48
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((x - radius, y - radius * 0.9, x + radius, y + radius * 1.1), fill=(0, 0, 0, 100))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(radius * 0.12)))
    draw = ImageDraw.Draw(image)
    outline = WHITE_EDGE if color == WHITE else color
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius), fill=color, outline=outline, width=round(radius * 0.05)
    )
    if color == BLACK:
        _draw_light(image, center, radius)


def _draw_light(image: Image.Image, center: tuple[float, float], radius: float) -> None:
    """Draw the soft light at the upper left of a black stone."""
    x, y = center
    light = Image.new("RGBA", image.size, (0, 0, 0, 0))
    small = radius * 0.45
    lx, ly = x - radius * 0.3, y - radius * 0.32
    ImageDraw.Draw(light).ellipse((lx - small, ly - small, lx + small, ly + small), fill=(255, 255, 255, 70))
    image.alpha_composite(light.filter(ImageFilter.GaussianBlur(radius * 0.18)))


def _draw_mark(draw: ImageDraw.ImageDraw, center: tuple[float, float], step: float, color: tuple) -> None:
    """Draw the small square that marks a point of territory."""
    x, y = center
    half = step * 0.13
    outline = WHITE_EDGE if color == WHITE else color
    draw.rectangle(
        (x - half, y - half, x + half, y + half), fill=color, outline=outline, width=max(1, round(step * 0.02))
    )


def main() -> None:
    """Read the output folder, and write the icons."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="the folder for kentogo.png, kentogo.ico and kentogo.icns")
    parser.add_argument("--window-icon", type=Path, help="also write the icon of the window to this PNG file")
    arguments = parser.parse_args()
    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    large = draw_icon(LARGE_SIZE, LARGE)
    large.save(output / "kentogo.png")
    large.save(output / "kentogo.icns")
    icons = [draw_icon(size, SMALL if size in SMALL_SIZES else LARGE) for size in ICO_SIZES]
    icons[-1].save(output / "kentogo.ico", sizes=[(size, size) for size in ICO_SIZES], append_images=icons[:-1])
    print(f"wrote kentogo.png, kentogo.ico and kentogo.icns in {output}")
    if arguments.window_icon is not None:
        draw_icon(WINDOW_ICON_SIZE, LARGE).save(arguments.window_icon)
        print(f"wrote {arguments.window_icon}")


if __name__ == "__main__":
    main()
