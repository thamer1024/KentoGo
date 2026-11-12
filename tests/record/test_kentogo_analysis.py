"""Tests for kentogo.record.kentogo_analysis (KentoGo's own analysis data, the KGA property)."""

from pysgf import GoNode

from kentogo.record.katrain_kt import encode_kt
from kentogo.record.kentogo_analysis import (
    KGA_PROPERTY,
    decode_kga,
    encode_kga,
    has_analysis,
    read_analysis,
    read_kentogo_analysis,
)

ANALYSIS = {
    "root": {"scoreLead": 1.5, "winrate": 0.6, "visits": 2500},
    "moves": {"Q16": {"scoreLead": 1.5, "order": 0, "pv": ["Q16", "D4"]}, "D4": {"scoreLead": 0.5, "order": 1}},
}


def node_with(**properties) -> GoNode:
    """A node with the given properties."""
    node = GoNode()
    for key, values in properties.items():
        node.properties[key] = values
    return node


def test_the_analysis_comes_back_with_its_numbers():
    """The values come back as they were; the areas and the policy come back as 16-bit numbers."""
    data = decode_kga(encode_kga({**ANALYSIS, "ownership": [0.5, -1.0], "policy": [0.25, 0.75, 0.0]}))
    assert (data["root"], data["moves"]) == (ANALYSIS["root"], ANALYSIS["moves"])
    assert (data["ownership"], data["policy"]) == ((0.5, -1.0), (0.25, 0.75, 0.0))


def test_without_areas_and_policy():
    """An analysis without areas and policy has None for them."""
    data = decode_kga(encode_kga({**ANALYSIS, "ownership": None}))
    assert (data["ownership"], data["policy"]) == (None, None)


def test_kentogo_analysis_comes_before_katrains():
    """A node with both reads KentoGo's; a node with KT only reads KaTrain's; a node with neither has none."""
    katrain = {"root": {"scoreLead": -3.0}, "moves": {}}
    both = node_with(**{KGA_PROPERTY: encode_kga(ANALYSIS), "KT": encode_kt(katrain)})
    assert read_analysis(both)["root"]["scoreLead"] == 1.5
    only_kt = node_with(KT=encode_kt(katrain))
    assert read_analysis(only_kt)["root"]["scoreLead"] == -3.0 and read_kentogo_analysis(only_kt) is None
    assert read_analysis(GoNode()) is None and read_analysis(None) is None
    assert has_analysis(both) and has_analysis(only_kt) and not has_analysis(GoNode())


def test_broken_data_is_none():
    """Data that cannot be read is treated as none."""
    assert read_analysis(node_with(**{KGA_PROPERTY: ["broken", "data"]})) is None
