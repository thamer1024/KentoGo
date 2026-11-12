"""KentoGo's own analysis data of a node: the KGD property (KentoGo Data).

KentoGo's analysis of every node is in its KGA property (see record.kentogo_analysis). KentoGo
writes more for the moves that can become problems (see analysis.analyze): how the
areas change with one move, the sequences until the position settles, the value of not answering
(tenuki), the moves that punish an opponent's mistake. Those data are kept as KataGo's numbers, not
as conclusions ("a big point was missed" and the like are worked out when they are shown), so that
new features can use them later without analyzing the games again.

The format is made to grow:
- The data is a JSON object with its format version ("v", FORMAT_VERSION). Readers look only at
  the keys they know and keep the others; a key added later does not need a new version.
- Board-sized lists of numbers (the areas, KataGo's ownership) are kept as Grid objects. They are
  written as 16-bit floats (KaTrain's own packing, vendor.katrain_analysis.pack_floats) in a second
  value, so that they take little room; the JSON has {"grid": index} in their place.
- Both values are gzip-compressed and base64-encoded, as KaTrain writes KT.

KaTrain keeps a property it does not know when it saves a game (its GameNode.add_list_property gives
it to pysgf), so KGD stays in a game that KaTrain opens and saves again. KaTrain may analyze the game
again then; "base" in the data (the score and the visits of the analysis it was made from) lets
KentoGo see that the data is older than the analysis.
"""

from __future__ import annotations

import base64
import gzip
import json
from dataclasses import dataclass

from kentogo.vendor.katrain_analysis import pack_floats, unpack_floats

KGD_PROPERTY = "KGD"
FORMAT_VERSION = 1
_GRID_KEY = "grid"


@dataclass(frozen=True)
class Grid:
    """A board-sized list of numbers (such as KataGo's ownership), kept in 16 bits each in the file.

    Attributes:
        values: The numbers, in KataGo's order (row by row from the top).
    """

    values: tuple[float, ...]


def encode_kgd(data: dict) -> list[str]:
    """Return the values of the KGD property for the data (FORMAT_VERSION is put in as "v").

    Raises:
        TypeError: If the data has something that JSON cannot keep (other than Grid objects).
    """
    grids: list[Grid] = []
    main = json.dumps({**_without_grids(data, grids), "v": FORMAT_VERSION}, separators=(",", ":"))
    numbers = b"".join(pack_floats(grid.values) for grid in grids)
    sizes = [len(grid.values) for grid in grids]
    header = json.dumps(sizes, separators=(",", ":"))
    return [_zip(main.encode("utf-8")), _zip(header.encode("utf-8") + b"\n" + numbers)]


def decode_kgd(values: list[str]) -> dict:
    """Return the data of a KGD property, with its grids as Grid objects.

    Raises:
        ValueError: If the values cannot be read.
    """
    try:
        main = json.loads(_unzip(values[0]))
        header, _, numbers = _unzip(values[1]).partition(b"\n")
        sizes = json.loads(header)
        grids, start = [], 0
        for size in sizes:
            grids.append(Grid(tuple(unpack_floats(numbers[start : start + 2 * size], size))))
            start += 2 * size
    except (IndexError, ValueError, TypeError, OSError, EOFError) as error:  # Broken base64, gzip, JSON or numbers.
        raise ValueError(f"KentoGo's analysis data cannot be read: {error}") from error
    if not isinstance(main, dict) or not isinstance(main.get("v"), int):
        raise ValueError("KentoGo's analysis data has no format version")
    return _with_grids(main, grids)


def read_kgd(node) -> dict | None:
    """Return the KentoGo data of a node (a pysgf node), or None when it has none or it cannot be read."""
    values = node.get_list_property(KGD_PROPERTY, [])
    if not values:
        return None
    try:
        return decode_kgd(values)
    except ValueError:
        return None


def write_kgd(node, data: dict | None) -> None:
    """Write the KentoGo data into a node (a pysgf node), or remove it when data is None."""
    if data is None:
        node.properties.pop(KGD_PROPERTY, None)
    else:
        node.properties[KGD_PROPERTY] = encode_kgd(data)


def _without_grids(value: object, grids: list[Grid]) -> object:
    """Return the value with each Grid replaced by {"grid": its index in grids} (grids is filled)."""
    if isinstance(value, Grid):
        grids.append(value)
        return {_GRID_KEY: len(grids) - 1}
    if isinstance(value, dict):
        return {key: _without_grids(item, grids) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_without_grids(item, grids) for item in value]
    return value


def _with_grids(value: object, grids: list[Grid]) -> object:
    """Return the value with each {"grid": index} replaced by its Grid."""
    if isinstance(value, dict):
        if set(value) == {_GRID_KEY} and isinstance(value[_GRID_KEY], int):
            return grids[value[_GRID_KEY]]
        return {key: _with_grids(item, grids) for key, item in value.items()}
    if isinstance(value, list):
        return [_with_grids(item, grids) for item in value]
    return value


def _zip(data: bytes) -> str:
    return base64.standard_b64encode(gzip.compress(data)).decode("utf-8")


def _unzip(text: str) -> bytes:
    return gzip.decompress(base64.standard_b64decode(text))
