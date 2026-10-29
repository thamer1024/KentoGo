"""Tests for kentogo.common.sgf."""

import pytest
from pysgf import GoGame

from kentogo.common.sgf import board_size, komi, load_game, main_line, node_move, rules, setup_stones
from kentogo.common.types import Move


def parse(text: str):
    """Read an SGF text and return the root node."""
    return GoGame.parse_sgf(text)


def gtp_moves(nodes) -> list[str]:
    """Return the moves of the nodes as GTP text, such as "B:Q16"."""
    return [f"{m.color}:{m.gtp()}" for m in map(node_move, nodes) if m is not None]


def test_load_game(tmp_path):
    """A file is read with the encoding given in the CA property."""
    path = tmp_path / "game.sgf"
    path.write_text("(;CA[UTF-8]SZ[19]PB[黒の人];B[pd])", encoding="utf-8")
    root = load_game(path)
    assert root.get_property("PB") == "黒の人"


def test_game_information():
    """Board size, komi and rules are read from the root node."""
    root = parse("(;SZ[13]KM[0.5]RU[chinese])")
    assert (board_size(root), komi(root), rules(root)) == (13, 0.5, "chinese")


def test_missing_game_information():
    """Missing values become the defaults."""
    root = parse("(;GM[1])")
    assert (board_size(root), komi(root), rules(root)) == (19, 6.5, "japanese")


def test_board_that_is_not_square():
    """A board that is not square is not supported."""
    with pytest.raises(ValueError):
        board_size(parse("(;SZ[9:13])"))


def test_setup_stones():
    """Handicap stones on the root node are returned, including a range such as "aa:bb"."""
    root = parse("(;SZ[9]AB[gc][cg]AW[aa:ab])")
    stones = setup_stones(root)
    assert sorted((s.color, s.gtp()) for s in stones) == [("B", "C3"), ("B", "G7"), ("W", "A8"), ("W", "A9")]


def test_node_move():
    """A node gives its move, a pass, or None if it has no move."""
    root = parse("(;SZ[19];B[pd];W[];C[only a comment])")
    nodes = main_line(root)
    assert node_move(nodes[1]) == Move.from_gtp("Q16", "B")
    assert node_move(nodes[2]).is_pass
    assert node_move(nodes[3]) is None


def test_main_line_without_branches():
    """Without branches, the main line is all nodes."""
    root = parse("(;SZ[19];B[pd];W[dd];B[pp])")
    assert gtp_moves(main_line(root)) == ["B:Q16", "W:D16", "B:Q4"]


def test_main_line_follows_the_longest_branch():
    """The main line is the longest line, even when it is not the first branch.

    This is how KaTrain saves a teaching game: the move taken back (B:A1) is
    a short branch, and the real game continues in another branch.
    """
    root = parse("(;SZ[19];B[pd];W[dd](;B[as])(;B[pp];W[dp](;B[aa])(;B[cc];W[qq])))")
    assert gtp_moves(main_line(root)) == ["B:Q16", "W:D16", "B:Q4", "W:D4", "B:C17", "W:R3"]


def test_main_line_tie_takes_the_first_branch():
    """When two branches have the same length, the first one is used."""
    root = parse("(;SZ[19];B[pd](;W[dd])(;W[dp]))")
    assert gtp_moves(main_line(root)) == ["B:Q16", "W:D16"]


def test_main_line_of_a_long_game():
    """A long game does not cause a recursion error."""
    moves = "".join(
        f";{'BW'[i % 2]}[{'abcdefghijklmnopqrs'[i % 19]}{'abcdefghijklmnopqrs'[i // 19 % 19]}]" for i in range(3000)
    )
    root = parse(f"(;SZ[19]{moves})")
    assert len(main_line(root)) == 3001
