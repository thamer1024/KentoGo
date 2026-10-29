"""Read SGF files (with pysgf) and get the moves of the game.

pysgf reads the file and keeps it as a tree of nodes. This module turns the
nodes into the data of common.types, and finds the moves of the real game.
"""

from __future__ import annotations

from pathlib import Path

from pysgf import GoGame, GoNode

from kentogo.common.rules import DEFAULT_RULES
from kentogo.common.types import Move


def load_game(path: str | Path) -> GoNode:
    """Read an SGF file.

    Args:
        path: Path of the file. The text encoding is found from the CA property.

    Returns:
        The root node of the game tree.
    """
    return GoGame.from_file(str(path)).root


def board_size(root: GoNode) -> int:
    """Return the size of the board.

    Args:
        root: The root node.

    Raises:
        ValueError: If the board is not square (KentoGo supports only square boards).
    """
    width, height = root.board_size
    if width != height:
        raise ValueError(f"the board is not square: {width}x{height}")
    return width


def komi(root: GoNode) -> float:
    """Return the komi of the game (6.5 if the file does not have it, as in pysgf)."""
    return root.komi


def rules(root: GoNode) -> str:
    """Return the RU property of the game, or the default rules if it is missing."""
    return root.get_property("RU", DEFAULT_RULES)


def setup_stones(root: GoNode) -> tuple[Move, ...]:
    """Return the stones placed on the root node, such as handicap stones (AB and AW).

    Stones placed on later nodes are not supported, because KaTrain and Fox Weiqi
    put all setup stones on the root node.
    """
    return tuple(_to_move(move) for move in root.placements)


def node_move(node: GoNode) -> Move | None:
    """Return the move of a node, or None if the node has no move.

    A node has at most one move in a normal SGF file. If it has more, the first one is used.
    """
    moves = node.moves
    return _to_move(moves[0]) if moves else None


def main_line(root: GoNode) -> list[GoNode]:
    """Return the nodes of the real game, from the root to the last move.

    In KaTrain, a move taken back in a teaching game, and moves tried by the user,
    stay in the file as branches. The first branch is not always the real game,
    but the real game is the longest line. So at each branch, this follows the child
    with the longest line below it (the first such child if there is a tie).

    Args:
        root: The root node.

    Returns:
        The nodes, starting with the root.
    """
    heights = _heights(root)
    nodes = [root]
    node = root
    while node.children:
        node = max(node.children, key=lambda child: heights[id(child)])
        nodes.append(node)
    return nodes


def _heights(root: GoNode) -> dict[int, int]:
    """Return the length of the longest line below each node, keyed by id(node).

    The tree is walked without recursion, because a game can have hundreds of moves.
    """
    heights: dict[int, int] = {}
    order = []
    stack = [root]
    while stack:
        node = stack.pop()
        order.append(node)
        stack.extend(node.children)
    for node in reversed(order):  # Children come after their parent in order.
        heights[id(node)] = 1 + max((heights[id(child)] for child in node.children), default=0)
    return heights


def _to_move(move) -> Move:
    """Turn a pysgf Move into a Move of common.types."""
    return Move(move.player, tuple(move.coords) if move.coords is not None else None)
