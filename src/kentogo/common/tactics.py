"""What a move does on the board, told from the stones alone (without KataGo): captures, ataris, ladders, shapes.

Some of these are sure, as they follow from the rules (SURE): the move captures stones (a pon-nuki
when it takes one stone from all four sides), takes a ko, puts one group or two groups of the opponent
in atari, connects two of the player's groups, saves a group that was in atari, starts a ladder that
captures the group (read on the board to the end, see _ladder_captures), makes an empty triangle, or
puts its own stones in atari. The others are the names of the shape (cut, wedge, hane, sagari, nobi,
tsuke, kosumi, ikken, keima; see common.shapes) and a move far from the opponent's last move: they
follow fixed definitions, but a player may name a move otherwise, so the quiz screen marks them with a
question mark (GUESSED).
"""

from __future__ import annotations

from kentogo.common.board import Board, IllegalMoveError, Point
from kentogo.common.shapes import (
    CONNECT,
    CUT,
    HANE,
    IKKEN,
    KEIMA,
    KOSUMI,
    NOBI,
    SAGARI,
    TSUKE,
    WEDGE,
    empty_triangle,
    neighbors,
    shapes_of,
)
from kentogo.common.types import Move, opponent

CAPTURE = "capture"
PON_NUKI = "pon_nuki"
KO = "ko"
ATARI = "atari"
DOUBLE_ATARI = "double_atari"
ESCAPE = "escape"
LADDER = "ladder"
EMPTY_TRIANGLE = "empty_triangle"
SELF_ATARI = "self_atari"
FAR = "far"
SURE = (CAPTURE, PON_NUKI, KO, ATARI, DOUBLE_ATARI, CONNECT, ESCAPE, LADDER, EMPTY_TRIANGLE, SELF_ATARI)
GUESSED = (CUT, WEDGE, HANE, SAGARI, NOBI, TSUKE, KOSUMI, IKKEN, KEIMA, FAR)

FAR_DISTANCE = 5  # A move at least this far (in rows or columns) from the opponent's last move is far from it.
LADDER_MOVES = 200  # The most moves of a ladder that are read.
LADDER_STEPS = 3  # A chase is a ladder when the group runs at least this many times (else it is only an atari).


def tactics(board: Board, move: Move, last_move: Move | None) -> tuple[str, ...]:
    """Return what a move does on a board, the sure ones first (see SURE and GUESSED).

    Args:
        board: The board before the move (not changed).
        move: The move.
        last_move: The opponent's last move, or None.

    Returns:
        The names (CAPTURE, ATARI, ...), or () for a pass or a move that cannot be played.
    """
    if move.coord is None:
        return ()
    after = board.copy()
    try:
        captured = after.play(move)
    except IllegalMoveError:
        return ()
    sure = _captures(after, captured, move) + _ataris(board, after, move) + _own_groups(board, after, move)
    sure += _own_shape(after, move)
    return sure + _guesses(board, move, last_move, sure)


def _captures(after: Board, captured: list[Point], move: Move) -> tuple[str, ...]:
    """Return KO when the move took a ko, PON_NUKI when it took one stone from all sides, else CAPTURE."""
    if not captured:
        return ()
    if after.ko_point is not None:
        return (KO,)
    around = neighbors(after, captured[0])
    # On the edge a stone has fewer than four sides: that is no pon-nuki.
    if len(captured) == 1 and len(around) == 4 and all(after.stone_at(point) == move.color for point in around):
        return (PON_NUKI,)
    return (CAPTURE,)


def _own_shape(after: Board, move: Move) -> tuple[str, ...]:
    """Return EMPTY_TRIANGLE and SELF_ATARI when the move makes them."""
    found = (EMPTY_TRIANGLE,) if empty_triangle(after, move.coord, move.color) else ()
    if len(after.liberties(after.group_at(move.coord))) == 1:
        found += (SELF_ATARI,)
    return found


def _ataris(before: Board, after: Board, move: Move) -> tuple[str, ...]:
    """Return ATARI (and LADDER when the chase captures the group) or DOUBLE_ATARI for the new ataris."""
    groups = _new_ataris(before, after, move)
    if len(groups) >= 2:
        return (DOUBLE_ATARI,)
    if not groups:
        return ()
    return (ATARI, LADDER) if _ladder_captures(after, next(iter(groups)), move.color) else (ATARI,)


def _new_ataris(before: Board, after: Board, move: Move) -> set[frozenset[Point]]:
    """Return the opponent's groups next to the move that are in atari now, and were not before."""
    groups = _neighbor_groups(after, move.coord, opponent(move.color))
    return {group for group in groups if len(after.liberties(group)) == 1 and _liberty_count(before, group) > 1}


def _own_groups(before: Board, after: Board, move: Move) -> tuple[str, ...]:
    """Return CONNECT when the move joins two of the player's groups, ESCAPE when it saves one in atari."""
    groups = _neighbor_groups(before, move.coord, move.color)
    found = (CONNECT,) if len(groups) >= 2 else ()
    in_atari = any(len(before.liberties(group)) == 1 for group in groups)
    if in_atari and len(after.liberties(after.group_at(move.coord))) >= 2:
        found += (ESCAPE,)
    return found


def _guesses(before: Board, move: Move, last_move: Move | None, sure: tuple[str, ...]) -> tuple[str, ...]:
    """Return the names of the shape (without CONNECT, which is sure), or a move far from the last move."""
    found = tuple(shape.name for shape in shapes_of(before, move) if shape.name != CONNECT)
    if not sure and not found and _is_far(move, last_move):
        found += (FAR,)
    return found


def _is_far(move: Move, last_move: Move | None) -> bool:
    """True if the move is at least FAR_DISTANCE rows or columns away from the opponent's last move."""
    if last_move is None or last_move.coord is None:
        return False
    (x, y), (last_x, last_y) = move.coord, last_move.coord
    return max(abs(x - last_x), abs(y - last_y)) >= FAR_DISTANCE


def _ladder_captures(board: Board, group: frozenset[Point], attacker: str) -> bool:
    """True if a group in atari is captured by a ladder: it runs at least LADDER_STEPS times and still dies.

    The group runs to its only liberty, or takes a stone of the attacker that is in atari; the attacker
    then puts it in atari again from either side. When it has three liberties or more, it has escaped.
    """
    return _chase(board, next(iter(group)), attacker, LADDER_MOVES) >= LADDER_STEPS


def _chase(board: Board, stone: Point, attacker: str, moves_left: int) -> int:
    """Return how many times the group of a stone in atari ran before it was captured, or -1 if it escapes."""
    if moves_left <= 0:
        return -1
    defender = opponent(attacker)
    for escape in _escapes(board, stone, defender):
        result = _after_escape(board, stone, escape, attacker, moves_left)
        if result < 0:
            return -1
    return _runs_until_captured(board, stone, attacker, moves_left)


def _escapes(board: Board, stone: Point, defender: str) -> list[Move]:
    """Return the defender's moves that take a stone of the attacker in atari next to the group."""
    group = board.group_at(stone)
    attackers = {
        frozenset(board.group_at(p))
        for s in group
        for p in neighbors(board, s)
        if board.stone_at(p) == opponent(defender)
    }
    return [Move(defender, next(iter(board.liberties(g)))) for g in attackers if len(board.liberties(g)) == 1]


def _after_escape(board: Board, stone: Point, escape: Move, attacker: str, moves_left: int) -> int:
    """Play a capture of the defender, and return -1 if the group then escapes (else 0)."""
    after = board.copy()
    try:
        after.play(escape)
    except IllegalMoveError:
        return 0
    return -1 if len(after.liberties(after.group_at(stone))) >= 2 else 0


def _runs_until_captured(board: Board, stone: Point, attacker: str, moves_left: int) -> int:
    """Run the group to its only liberty, and let the attacker chase it (see _chase)."""
    liberties = board.liberties(board.group_at(stone))
    if len(liberties) != 1:
        return -1
    after = board.copy()
    try:
        after.play(Move(opponent(attacker), next(iter(liberties))))
    except IllegalMoveError:
        return 0  # The group cannot run: it is captured.
    count = len(after.liberties(after.group_at(stone)))
    if count <= 1:
        return 1  # Running gives nothing: the group is captured.
    if count >= 3:
        return -1
    return _attack(after, stone, attacker, moves_left - 1)


def _attack(board: Board, stone: Point, attacker: str, moves_left: int) -> int:
    """Put the group (two liberties) in atari from each side; return the runs if one way captures it, else -1."""
    for point in sorted(board.liberties(board.group_at(stone))):
        after = board.copy()
        try:
            after.play(Move(attacker, point))
        except IllegalMoveError:
            continue
        if len(after.liberties(after.group_at(point))) < 2 or not after.stone_at(stone):
            continue  # The attacking stone could be taken at once.
        runs = _chase(after, stone, attacker, moves_left - 1)
        if runs >= 0:
            return runs + 1
    return -1


def _neighbor_groups(board: Board, point: Point, color: str) -> set[frozenset[Point]]:
    """Return the groups of a color next to a point."""
    return {board.group_at(p) for p in neighbors(board, point) if board.stone_at(p) == color}


def _liberty_count(board: Board, group: frozenset[Point]) -> int:
    """Return the liberties that the group of a group's first stone had on another board (the board before)."""
    return len(board.liberties(board.group_at(next(iter(group)))))
