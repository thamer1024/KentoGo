"""Tests for kentogo.record.kentogo_data (KentoGo's own analysis data, the KGD property)."""

import pytest
from pysgf import GoGame

from kentogo.record.kentogo_data import FORMAT_VERSION, KGD_PROPERTY, Grid, decode_kgd, encode_kgd, read_kgd, write_kgd

OWNERSHIP = Grid(tuple((index % 21 - 10) / 10 for index in range(361)))


def test_data_and_grids_go_through_the_file():
    data = {"base": {"scoreLead": -2.5, "visits": 500}, "played": {"pv": ["D4", "Q16"], "ownership": OWNERSHIP}}
    decoded = decode_kgd(encode_kgd(data))
    assert decoded["v"] == FORMAT_VERSION and decoded["base"] == data["base"]
    assert decoded["played"]["pv"] == ["D4", "Q16"]
    grid = decoded["played"]["ownership"]
    assert isinstance(grid, Grid) and len(grid.values) == 361
    assert max(abs(a - b) for a, b in zip(grid.values, OWNERSHIP.values, strict=True)) < 0.001  # 16 bits each.


def test_several_grids_and_lists_keep_their_order():
    data = {"lines": [{"ownership": Grid((0.5, -0.5))}, {"ownership": Grid((1.0,))}], "end": Grid((0.25,) * 3)}
    decoded = decode_kgd(encode_kgd(data))
    assert [line["ownership"].values for line in decoded["lines"]] == [(0.5, -0.5), (1.0,)]
    assert decoded["end"].values == (0.25, 0.25, 0.25)


def test_a_node_keeps_the_data_through_an_sgf_file():
    """The property survives writing and reading the SGF text, as when KaTrain saves the game again."""
    root = GoGame.parse_sgf("(;SZ[19];B[pd];W[dd])")
    move = root.nodes_in_tree[2]
    write_kgd(move, {"kind": "move", "areas": OWNERSHIP, "later": {"added": True}})
    again = GoGame.parse_sgf(root.sgf()).nodes_in_tree[2]
    data = read_kgd(again)
    assert data["kind"] == "move" and data["later"] == {"added": True} and len(data["areas"].values) == 361
    assert read_kgd(again.parent) is None
    write_kgd(again, None)
    assert KGD_PROPERTY not in again.properties


def test_the_data_stays_small():
    """A board of numbers takes about 2 bytes a point (KaTrain's KT keeps two such boards for every node)."""
    values = encode_kgd({"areas": OWNERSHIP, "best": OWNERSHIP})
    assert sum(len(value) for value in values) < 4 * 361 * 2


@pytest.mark.parametrize("values", [[], ["not base64"], [encode_kgd({})[0]], encode_kgd({})[1:] * 2])
def test_broken_data_is_not_read(values):
    with pytest.raises(ValueError):
        decode_kgd(values)
    node = GoGame.parse_sgf("(;SZ[9];B[ee])").nodes_in_tree[1]
    if values:
        node.properties[KGD_PROPERTY] = values
    assert read_kgd(node) is None
