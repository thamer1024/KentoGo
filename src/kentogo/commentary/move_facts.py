"""The facts about the shapes around one of the user's mistakes, worked out from the board (see common.shapes).

These facts are given to the AI as facts, so that it names shapes and places from them instead of
reading the diagrams (which an AI does badly):

- the shape of the opponent's previous move, of the played move and of the best move, and what each one
  does (stones captured, stones put in atari, a pon-nuki, an empty triangle, a self-atari);
- the moves of the game after the mistake (the played move and the opponent's real reply), with their shapes;
- the shape of each move of the predicted sequence;
- how far the opponent's next move of the predicted sequence is from the best move (when it is far, the
  opponent left the place: the prompt tells only that, and the AI says whether the best move was sente);
- the user's cutting points before the move, after the game's moves, and after the predicted sequence;
- the user's groups near the point that the opponent most wanted to play after the played move
  (the opponent's best move): the groups that were aimed at.

The same facts as the user's own prototype (kento_prompt, builder.py), written again for KentoGo.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.common.board import Board, IllegalMoveError, Point
from kentogo.common.shapes import Shape, cut_points, shapes_of
from kentogo.common.tactics import EMPTY_TRIANGLE, KO, LADDER, PON_NUKI, SELF_ATARI, tactics
from kentogo.common.types import Move

TARGET_DISTANCE = 2  # The user's groups this close to the opponent's best move were aimed at.
EFFECTS = (PON_NUKI, KO, LADDER, EMPTY_TRIANGLE, SELF_ATARI)  # What a move does, besides captures and ataris.


@dataclass(frozen=True)
class GroupInfo:
    """A group of stones.

    Attributes:
        color: "B" or "W".
        stones: The points of the stones, sorted.
        liberties: The number of liberties.
    """

    color: str
    stones: tuple[Point, ...]
    liberties: int


@dataclass(frozen=True)
class ShapedMove:
    """A move with its shape and what it does on the board.

    Attributes:
        move: The move.
        shapes: The names of its shape (see common.shapes.shapes_of).
        captured: The stones that it takes (sorted).
        in_atari: The groups that it puts in atari (one liberty left, and not in atari before it).
        effects: What else it does, from EFFECTS (see common.tactics).
    """

    move: Move
    shapes: tuple[Shape, ...]
    captured: tuple[Point, ...]
    in_atari: tuple[GroupInfo, ...]
    effects: tuple[str, ...]


@dataclass(frozen=True)
class MoveFacts:
    """The facts about the shapes around a mistake (see the module).

    Attributes:
        last_move: The opponent's previous move, or None.
        played: The played move.
        best: The best move (the first move of the sequence), or None.
        game: The played move and the opponent's real reply after it (when there is one).
        pv: The moves of the predicted sequence (from the best move).
        reply_distance: How far (in rows or columns) the second move of the sequence is from the best move.
        cuts_before: The user's cutting points before the move.
        cuts_after_game: Those after the game's moves (the played move and the reply).
        cuts_after_pv: Those after the predicted sequence.
        aimed_at: The user's groups near the opponent's best move after the played move.
    """

    last_move: ShapedMove | None
    played: ShapedMove
    best: ShapedMove | None
    game: tuple[ShapedMove, ...]
    pv: tuple[ShapedMove, ...]
    reply_distance: int | None
    cuts_before: tuple[Point, ...]
    cuts_after_game: tuple[Point, ...]
    cuts_after_pv: tuple[Point, ...]
    aimed_at: tuple[GroupInfo, ...]


@dataclass(frozen=True)
class GameMoves:
    """The moves of the game around a mistake.

    Attributes:
        last_move: The opponent's previous move, or None at the start.
        reply: The opponent's real reply after the played move, or None.
        opponent_best: The opponent's best move after the played move (from the analysis), or None.
    """

    last_move: Move | None
    reply: Move | None
    opponent_best: Move | None


def move_facts(
    before_last: Board | None, before: Board, played: Move, sequence: tuple[Move, ...], game: GameMoves
) -> MoveFacts:
    """Work out the facts about a mistake.

    Args:
        before_last: The board before the opponent's previous move, or None at the start.
        before: The board before the played move.
        played: The played move.
        sequence: The predicted sequence from the position before the played move (it starts with the best move).
        game: The moves of the game around the mistake.
    """
    color = played.color
    game_moves, after_game = play_shaped(before, (played, game.reply) if game.reply is not None else (played,))
    pv, after_pv = play_shaped(before, sequence)
    last_move = shaped(before_last, game.last_move) if before_last is not None and game.last_move else None
    return MoveFacts(
        last_move=last_move,
        played=game_moves[0] if game_moves else ShapedMove(played, (), (), (), ()),
        best=pv[0] if pv else None,
        game=game_moves,
        pv=pv,
        reply_distance=_distance(sequence[0], sequence[1]) if len(sequence) >= 2 else None,
        cuts_before=tuple(cut_points(before, color)),
        cuts_after_game=tuple(cut_points(after_game, color)),
        cuts_after_pv=tuple(cut_points(after_pv, color)),
        aimed_at=_aimed_at(before, played, game.opponent_best),
    )


def _aimed_at(before: Board, played: Move, opponent_best: Move | None) -> tuple[GroupInfo, ...]:
    """Return the user's groups near the opponent's best move after the played move (none without one)."""
    if opponent_best is None or opponent_best.coord is None:
        return ()
    after = before.copy()
    try:
        after.play(played)
    except IllegalMoveError:
        return ()
    groups = [group for group in all_groups(after) if group.color == played.color]
    return tuple(group for group in groups if _group_distance(group, opponent_best.coord) <= TARGET_DISTANCE)


def shaped(board: Board, move: Move) -> ShapedMove | None:
    """Return a move with its shape and what it does on a board (not changed), or None if it cannot be played."""
    moves, _after = play_shaped(board, (move,))
    return moves[0] if moves else None


def play_shaped(board: Board, moves: tuple[Move, ...]) -> tuple[tuple[ShapedMove, ...], Board]:
    """Play moves on a copy of a board, with the shape of each; stop at a move that cannot be played.

    Returns:
        The moves with their shapes, and the board after them.
    """
    board = board.copy()
    found = []
    for move in moves:
        names = tactics(board, move, None) if move.coord is not None else ()
        shapes = shapes_of(board, move)
        atari_before = {group.stones for group in groups_in_atari(board)}
        try:
            captured = board.play(move)
        except IllegalMoveError:
            break
        in_atari = tuple(group for group in groups_in_atari(board) if group.stones not in atari_before)
        effects = tuple(name for name in EFFECTS if name in names)
        found.append(ShapedMove(move, shapes, tuple(sorted(captured)), in_atari, effects))
    return tuple(found), board


def groups_in_atari(board: Board) -> tuple[GroupInfo, ...]:
    """Return all groups on the board that have only one liberty."""
    return tuple(group for group in all_groups(board) if group.liberties == 1)


def all_groups(board: Board) -> list[GroupInfo]:
    """Return every group on the board, in the order of their first stone."""
    seen: set[Point] = set()
    groups = []
    for point, color in sorted(board.stones().items()):
        if point in seen:
            continue
        stones = board.group_at(point)
        seen |= stones
        groups.append(GroupInfo(color, tuple(sorted(stones)), len(board.liberties(stones))))
    return groups


def _distance(first: Move, second: Move) -> int | None:
    """Return how far two moves are (in rows or columns), or None for a pass."""
    if first.coord is None or second.coord is None:
        return None
    return max(abs(first.coord[0] - second.coord[0]), abs(first.coord[1] - second.coord[1]))


def _group_distance(group: GroupInfo, point: Point) -> int:
    """Return how far the nearest stone of a group is from a point."""
    return min(max(abs(x - point[0]), abs(y - point[1])) for x, y in group.stones)
