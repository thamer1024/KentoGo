"""Colors and images of the screens, the same as KaTrain's default theme.

The values come from KaTrain (katrain/gui/theme.py), and the images from
katrain/img. KaTrain is under the MIT license: see THIRD_PARTY_NOTICES.md.
Colors are (red, green, blue, alpha), from 0 to 1.
"""

from __future__ import annotations

from pathlib import Path

IMAGES = Path(__file__).resolve().parent.parent / "images"

# Screen.
BACKGROUND_COLOR = (36 / 255, 48 / 255, 62 / 255, 1)
BOX_BACKGROUND_COLOR = (46 / 255, 65 / 255, 88 / 255, 1)
BUTTON_COLOR = (64 / 255, 85 / 255, 110 / 255, 1)
BUTTON_DISABLED_COLOR = (50 / 255, 66 / 255, 85 / 255, 1)  # A button that cannot be pressed now.
TEXT_COLOR = (0.95, 0.95, 0.95, 1)
VERSION_TEXT_COLOR = (0.95, 0.95, 0.95, 0.5)  # The version at the bottom of the top screen.
APP_ICON = IMAGES / "app_icon.png"  # The icon of the window and the task bar (made by tools/make_icon.py).
MENU_IMAGE = IMAGES / "hamburger.png"  # The menu button, the same as KaTrain's.
MENU_BORDER_COLOR = (0.7, 0.7, 0.7, 1)  # The line around the open menu (KaTrain's LIGHT_GREY).

# Check boxes.
CHECKBOX_SELECTED_COLOR = (0.93, 0.93, 0.93, 1)
CHECKBOX_UNSELECTED_COLOR = (1, 1, 1, 0.7)
CHECKBOX_DISABLED_COLOR = (1, 1, 1, 0.12)

# Board.
BOARD_IMAGE = IMAGES / "board.png"
BOARD_TINT = (1, 1, 1, 1)  # Multiplied with the board image.
LINE_COLOR = (0, 0, 0, 1)
STONE_IMAGES = {"B": IMAGES / "B_stone.png", "W": IMAGES / "W_stone.png"}
STONE_SIZE = 0.505  # Half of the stone image size, in line spacings. The edge of the image is transparent.
NUMBER_COLORS = {"B": (0.95, 0.95, 0.95, 1), "W": (0.05, 0.05, 0.05, 1)}  # Numbers on stones.
LAST_MOVE_COLOR = (0.8, 0.1, 0.1, 1)


def flag_image(language: str) -> Path:
    """Return the flag image of a language (one of texts.LANGUAGES).

    The flags are round like KaTrain's, made from public domain flags by tools/make_flags.py.
    English has the flag of the UK, as in KaTrain.
    """
    country = "uk" if language == "en" else language
    return IMAGES / "flags" / f"flag-{country}.png"
