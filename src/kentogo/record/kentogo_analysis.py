"""KentoGo's own analysis data of a node: the KGA property (KentoGo Analysis).

KentoGo writes its analysis of a game (see analysis.analyze) in its own property, not in KaTrain's
KT: the KT property and its format are KaTrain's, so KentoGo only reads them, in the games that
KaTrain analyzed (see record.katrain_kt).

The data of a node is about the position after its move, as KataGo read it (only what the problems need,
see analysis.sgf_writer):
- "root": KataGo's values of the position (scoreLead and winrate from black's side, visits).
- "moves": the candidate next moves by their GTP point, each with KataGo's values
  (scoreLead and winrate after the move, visits, order, and pv for KataGo's best move).
- "taken_back" and "instinct": about the node's own move (KaTrain took it back in a teaching game; its
  first instinct, see analysis.sgf_writer._instinct).
- "ownership" and "policy": KataGo's areas and policy (row by row from the top; the policy has the
  pass last). KentoGo no longer writes them, but they are read in the files of older versions.

It is kept in KentoGo's container (see record.kentogo_data): a JSON object
with its format version, the board-sized lists of numbers as Grid objects in a second value, both
compressed. Readers look only at the keys they know.

read_analysis reads a node's analysis wherever it is: the KGA property when the node has one, else
KaTrain's KT (a game analyzed by KaTrain, or by an older KentoGo that wrote KT).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.record.katrain_kt import SUPPORTED_VERSION, decode_kt
from kentogo.record.kentogo_data import Grid, decode_kgd, encode_kgd

KGA_PROPERTY = "KGA"
_NUMBERS = ("ownership", "policy")  # The board-sized lists of numbers, kept as grids.


def encode_kga(analysis: dict) -> list[str]:
    """Return the values of the KGA property for the analysis of a node.

    Args:
        analysis: "root", "moves", and "ownership" and "policy" (lists of numbers, or None). Other keys are kept too.

    Raises:
        TypeError: If the analysis has something that JSON cannot keep.
    """
    data = {key: value for key, value in analysis.items() if key not in _NUMBERS}
    for key in _NUMBERS:
        if analysis.get(key):
            data[key] = Grid(tuple(analysis[key]))
    return encode_kgd(data)


def decode_kga(values: list[str]) -> dict:
    """Return the analysis of a KGA property, with "ownership" and "policy" as tuples (or None).

    Raises:
        ValueError: If the values cannot be read.
    """
    data = decode_kgd(values)
    data.pop("v", None)
    for key in _NUMBERS:
        grid = data.get(key)
        data[key] = grid.values if isinstance(grid, Grid) else None
    return data


@dataclass(frozen=True)
class Instinct:
    """The first instinct of a move: its place in KataGo's policy of the position before it.

    Attributes:
        rank: The move's rank in the policy (1 is KataGo's first instinct; 0 when it was not found).
        probability: The move's probability in the policy (0 to 1).
        best: The policy's first move (GTP).
        best_probability: Its probability (0 to 1).
    """

    rank: int
    probability: float
    best: str
    best_probability: float


def read_instinct(node) -> Instinct | None:
    """Return the first instinct of a node's move, kept in its KGA (a move that can become a problem), or None."""
    values = (read_kentogo_analysis(node) or {}).get("instinct")
    if not isinstance(values, dict):
        return None
    try:
        return Instinct(
            int(values["rank"]), float(values["probability"]), str(values["best"]), float(values["best_probability"])
        )
    except (KeyError, TypeError, ValueError):
        return None


def has_analysis(node) -> bool:
    """True if a node (a pysgf node) has analysis data: KentoGo's KGA or KaTrain's KT."""
    return bool(node.get_list_property(KGA_PROPERTY, [])) or bool(node.get_list_property("KT", []))


def read_kentogo_analysis(node) -> dict | None:
    """Return KentoGo's analysis of a node (its KGA property), or None if it has none or it cannot be read."""
    values = node.get_list_property(KGA_PROPERTY, []) if node is not None else []
    if not values:
        return None
    try:
        return decode_kga(values)
    except ValueError:
        return None


def read_analysis(node, kt_version: str = SUPPORTED_VERSION) -> dict | None:
    """Return the main analysis of a node ("root" and "moves"): its KGA, else KaTrain's KT, else None.

    Args:
        node: A pysgf node, or None.
        kt_version: The version of KaTrain's analysis data (the root's KTV property), for KT.
    """
    if node is None:
        return None
    analysis = read_kentogo_analysis(node)
    if analysis is not None:
        return analysis
    values = node.get_list_property("KT", [])
    if not values:
        return None
    try:
        return decode_kt(values, kt_version)
    except ValueError:
        return None
