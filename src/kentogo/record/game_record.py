"""A game read move by move, for looking through it and for the AI commentary.

The game is the main line (the real game, see common.sgf.main_line). Each move keeps
its comment split into its parts: the AI commentary (see record.ai_comment), the
user's notes, and KaTrain's evaluation (see record.katrain_comment).

Positions are numbered by the moves played: position 0 is the board before the first
move (with the setup stones, such as handicap stones), and position n is the board
after move n. The last position is the final position of the game.

Each move also keeps the other branches of the SGF file that start where it was played
(moves taken back by KaTrain in a teaching game, or moves the user tried), so that they
can be shown in place of the move.

Nothing here uses the screens, so the same record can be shown in any screen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pysgf import GoNode

from kentogo.common import sgf
from kentogo.common.board import Board, IllegalMoveError, Point
from kentogo.common.types import Move, Position
from kentogo.record.ai_comment import split_ai_comment
from kentogo.record.katrain_comment import KatrainMoveInfo, read_comment, split_comment


@dataclass(frozen=True)
class MoveRecord:
    """One move of the game, with its comment split into its parts.

    Attributes:
        number: The move number, from 1.
        move: The move.
        notes: The user's notes ("" if there are none).
        katrain: KaTrain's evaluation of the move, or None if KaTrain did not write one.
        katrain_text: The text that KaTrain wrote for the move, as it is ("" if there is none).
        ai_text: The AI commentary on the move ("" if there is none).
        ai_review: The AI review of the whole game, on the last move ("" if there is none).
        illegal: True if the move could not be played on the board (it is then left out of the positions).
        branches: The other lines of the SGF file that start in place of this move, each
            followed along its first children.
    """

    number: int
    move: Move
    notes: str = ""
    katrain: KatrainMoveInfo | None = None
    katrain_text: str = ""
    ai_text: str = ""
    ai_review: str = ""
    illegal: bool = False
    branches: tuple[tuple[Move, ...], ...] = ()


@dataclass(frozen=True)
class BoardState:
    """The board at one position.

    Attributes:
        stones: The stones, as a dict from point to color.
        captures: The number of stones taken by each color, as {"B": n, "W": n}.
    """

    stones: dict[Point, str]
    captures: dict[str, int]


@dataclass(frozen=True)
class GameRecord:
    """A whole game, move by move.

    Attributes:
        size: The size of the board.
        komi: The komi.
        rules: The rules, as written in the RU property.
        black_name: The PB property.
        white_name: The PW property.
        result: The RE property ("" if there is none).
        moves: The moves of the main line, in order.
        states: The board at each position (len(moves) + 1 of them, see the module docstring).
        setup: The stones placed before the first move, such as handicap stones.
    """

    size: int
    komi: float
    rules: str
    black_name: str
    white_name: str
    result: str
    moves: tuple[MoveRecord, ...]
    states: tuple[BoardState, ...]
    setup: tuple[Move, ...] = ()

    @property
    def last_position(self) -> int:
        """The number of the final position (the number of moves)."""
        return len(self.moves)

    def state(self, position: int) -> BoardState:
        """Return the board at a position. A number outside the game is moved to the first or the last position."""
        return self.states[clamp(position, self.last_position)]

    def final_state(self) -> BoardState:
        """Return the board at the end of the game."""
        return self.states[-1]

    def move_at(self, position: int) -> MoveRecord | None:
        """Return the move that made a position, or None for position 0."""
        return self.moves[position - 1] if 1 <= position <= self.last_position else None

    def position_after(self, count: int) -> Position:
        """Return the game position after `count` moves (a number outside the game is moved into it)."""
        return self.position_before(clamp(count, self.last_position) + 1)

    def position_before(self, position: int) -> Position:
        """Return the game position just before the move that made a position (the moves that could be played).

        Position 0 has no move before it, so the start of the game is returned for it.
        """
        played = tuple(record.move for record in self.moves[: max(position - 1, 0)] if not record.illegal)
        move = self.move_at(position)
        next_color = move.move.color if move is not None else "B"
        return Position(self.size, self.komi, self.rules, self.setup, played, next_color)

    def ai_positions(self) -> list[int]:
        """Return the positions whose move has an AI commentary or review, in order."""
        return [record.number for record in self.moves if record.ai_text or record.ai_review]


def read_game_record(root: GoNode) -> GameRecord:
    """Read a game into a record, move by move.

    Args:
        root: The root node of the game.

    Returns:
        The record.
    """
    nodes = sgf.main_line(root)
    moves = tuple(_move_records(nodes[1:]))
    states = _states(root, moves)
    return GameRecord(
        size=sgf.board_size(root),
        komi=sgf.komi(root),
        rules=sgf.rules(root),
        black_name=str(root.get_property("PB", "")),
        white_name=str(root.get_property("PW", "")),
        result=str(root.get_property("RE", "")),
        moves=tuple(_mark_illegal(moves, states.illegal)),
        states=states.states,
        setup=tuple(sgf.setup_stones(root)),
    )


def clamp(position: int, last_position: int) -> int:
    """Move a position number into 0 .. last_position."""
    return max(0, min(position, last_position))


def next_position(record: GameRecord, position: int, step: int = 1) -> int:
    """Return the position `step` moves later (or earlier, if step is negative), within the game."""
    return clamp(position + step, record.last_position)


def next_ai_position(record: GameRecord, position: int) -> int | None:
    """Return the first position after `position` whose move has an AI commentary, or None if there is none."""
    return next((number for number in record.ai_positions() if number > position), None)


def previous_ai_position(record: GameRecord, position: int) -> int | None:
    """Return the last position before `position` whose move has an AI commentary, or None if there is none."""
    return next((number for number in reversed(record.ai_positions()) if number < position), None)


def review_text(record: GameRecord) -> str:
    """Return the AI review of the whole game ("" if there is none)."""
    return next((move.ai_review for move in record.moves if move.ai_review), "")


def move_commentary(record: GameRecord, position: int) -> str:
    """Return the AI commentary on the move that made a position ("" if there is none)."""
    move = record.move_at(position)
    return move.ai_text if move is not None else ""


def read_move_record(node: GoNode, number: int) -> MoveRecord | None:
    """Read the move of a node with its comment split into its parts (None if the node has no move).

    The branches next to the node are not read (see read_game_record).

    Args:
        node: A node, on the main line or in a branch (such as a move taken back by KaTrain).
        number: The move number to give it.
    """
    move = sgf.node_move(node)
    if move is None:
        return None
    ai = split_ai_comment(str(node.get_property("C", "")))
    notes, info = read_comment(ai.rest)
    katrain_text = "\n".join(split_comment(ai.rest)[1])
    return MoveRecord(number, move, notes, info, katrain_text, ai.move_text, ai.review_text)


def _move_records(nodes: list[GoNode]) -> list[MoveRecord]:
    """Make a record of each node that has a move (nodes without a move are skipped)."""
    records = []
    for node in nodes:
        record = read_move_record(node, len(records) + 1)
        if record is not None:
            records.append(replace(record, branches=_branches(node)))
    return records


def _branches(node: GoNode) -> tuple[tuple[Move, ...], ...]:
    """Return the other lines that start in place of a node (its siblings), each along its first children."""
    parent = node.parent
    if parent is None:
        return ()
    lines = (_line(sibling) for sibling in parent.children if sibling is not node)
    return tuple(line for line in lines if line)


def _line(node: GoNode) -> tuple[Move, ...]:
    """Return the moves from a node along its first children (nodes without a move are skipped)."""
    moves = []
    current: GoNode | None = node
    while current is not None:
        move = sgf.node_move(current)
        if move is not None:
            moves.append(move)
        current = current.children[0] if current.children else None
    return tuple(moves)


@dataclass(frozen=True)
class _States:
    """The boards of all positions, and the numbers of the moves that could not be played."""

    states: tuple[BoardState, ...]
    illegal: frozenset[int]


def _states(root: GoNode, moves: tuple[MoveRecord, ...]) -> _States:
    """Play the moves on a board from the setup stones, and keep the board after each move.

    A move that cannot be played (it should not happen in a real game) is left out, so
    that the rest of the game can still be looked through.
    """
    start = Position(sgf.board_size(root), sgf.komi(root), sgf.rules(root), sgf.setup_stones(root), (), "B")
    board = Board.from_position(start)
    states = [_snapshot(board)]
    illegal = set()
    for record in moves:
        try:
            board.play(record.move)
        except IllegalMoveError:
            illegal.add(record.number)
        states.append(_snapshot(board))
    return _States(tuple(states), frozenset(illegal))


def _snapshot(board: Board) -> BoardState:
    """Return a copy of the stones and the captures of a board."""
    return BoardState(board.stones(), dict(board.captures))


def _mark_illegal(moves: tuple[MoveRecord, ...], illegal: frozenset[int]) -> list[MoveRecord]:
    """Return the moves, with `illegal` set on those that could not be played."""
    return [replace(record, illegal=True) if record.number in illegal else record for record in moves]
