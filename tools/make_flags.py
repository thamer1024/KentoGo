"""Make the round flag images of the languages from the public domain flags of region-flags.

The flags come from region-flags (https://github.com/fonttools/region-flags), which
collected them from Wikimedia Commons and checked that they are in the public domain.
This script cuts a circle out of each flag, so that the flags look like KaTrain's
round flag icons, and writes them as images/flags/flag-<code>.png (the names that
gui/theme.flag_image uses; English has the UK flag, as in KaTrain).

Most flags are cut in the middle. Some flags have their emblem near the pole, so
their circle is moved there (see CUT). The South Korean flag has its trigrams near
the corners, so the whole flag is put inside the circle on a white ground instead.

Usage:
    python tools/make_flags.py REGION_FLAGS_DIR OUTPUT_DIR

Example:
    python tools/make_flags.py ../region-flags src/kentogo/images/flags

Needs Pillow (not a dependency of KentoGo itself).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512  # Pixels, the same as KaTrain's flag icons.
SUPERSAMPLE = 4  # The circle is drawn larger and made smaller, for a smooth edge.

# The file name part of each language's flag, and the region-flags code of its country.
FLAGS = {
    "uk": "GB",
    "de": "DE",
    "fr": "FR",
    "ua": "UA",
    "es": "ES",
    "ru": "RU",
    "cn": "CN",
    "tw": "TW",
    "ko": "KR",
    "jp": "JP",
    "tr": "TR",
}
# Where the circle is cut across the flag: 0 at the pole, 0.5 in the middle, 1 at the other end.
CUT = {"CN": 0.0, "TW": 0.0, "ES": 0.2}
WHOLE = {"KR"}  # Flags put whole inside the circle.
WHITE = (255, 255, 255, 255)


def round_flag(flag: Image.Image, country: str) -> Image.Image:
    """Cut a round flag icon out of a flag image.

    Args:
        flag: The flag, wider than it is tall.
        country: The region-flags code of the country (it chooses how to cut).

    Returns:
        A SIZE x SIZE image, transparent outside the circle.
    """
    flag = flag.convert("RGBA")
    big = SIZE * SUPERSAMPLE
    if country in WHOLE:
        # The diagonal of the flag fits the circle.
        scale = big / (flag.width**2 + flag.height**2) ** 0.5
        small = flag.resize((round(flag.width * scale), round(flag.height * scale)), Image.LANCZOS)
        square = Image.new("RGBA", (big, big), WHITE)
        square.alpha_composite(small, ((big - small.width) // 2, (big - small.height) // 2))
    else:
        side = flag.height
        left = round((flag.width - side) * CUT.get(country, 0.5))
        square = flag.crop((left, 0, left + side, side)).resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    square.putalpha(mask)
    return square.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    """Read the arguments, and write one round flag for each language."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("region_flags", type=Path, help="the folder of region-flags (with png/)")
    parser.add_argument("output", type=Path, help="the folder to write the flags to")
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    for name, country in FLAGS.items():
        with Image.open(arguments.region_flags / "png" / f"{country}.png") as flag:
            round_flag(flag, country).save(arguments.output / f"flag-{name}.png", optimize=True)


if __name__ == "__main__":
    main()
