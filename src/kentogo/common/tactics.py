"""What a move does on the board, told from the stones alone (without KataGo): captures, ataris, ladders, shapes.

Some of these are sure, as they follow from the rules (SURE): the move captures stones, takes a ko,
puts one group or two groups of the opponent in atari, connects two of the player's groups, saves a
group that was in atari, or starts a ladder that captures the group (read on the board to the end, see
_ladder_captures). The others are only guesses (GUESSED): a cut, the name of the shape (tsuke, hane,
nobi, kosumi), and a move far from the opponent's last move. A guess can be wrong, so the screens mark
it with a question mark.
"""

from __future__ import annotations

from kentogo.common.board import Board, IllegalMoveError, Point
from kentogo.common.types import Move, opponent

CAPTURE = "capture"
KO = "ko"
ATARI = "atari"
DOUBLE_ATARI = "double_atari"
CONNECT = "connect"
ESCAPE = "escape"
LADDER = "ladder"
CUT = "cut"
TSUKE = "tsuke"
HANE = "hane"
NOBI = "nobi"
KOSUMI = "kosumi"
FAR = "far"
SURE = (CAPTURE, KO, ATARI, DOUBLE_ATARI, CONNECT, ESCAPE, LADDER)
GUESSED = (CUT, TSUKE, HANE, NOBI, KOSUMI, FAR)

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
    sure = _captures(after, captured) + _ataris(board, after, move) + _own_groups(board, after, move)
    return sure + _guesses(board, after, move, last_move, sure)


def _captures(after: Board, captured: list[Point]) -> tuple[str, ...]:
    """Return KO when the move took a ko, CAPTURE when it took other stones."""
    if not captured:
        return ()
    return (KO,) if after.ko_point is not None else (CAPTURE,)


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


def _guesses(before: Board, after: Board, move: Move, last_move: Move | None, sure: tuple[str, ...]) -> tuple[str, ...]:
    """Return the guesses: a cut, the name of the shape, or a move far from the opponent's last move."""
    found = (CUT,) if len(_neighbor_groups(after, move.coord, opponent(move.color))) >= 2 else ()
    shape = _shape(before, move)
    found += (shape,) if shape else ()
    if not sure and not found and _is_far(move, last_move):
        found += (FAR,)
    return found


def _shape(board: Board, move: Move) -> str:
    """Return the name of the shape of a move with the stones next to it (HANE, TSUKE, NOBI, KOSUMI), or ""."""
    point, color = move.coord, move.color
    mine = [p for p in _neighbors(board, point) if board.stone_at(p) == color]
    theirs = [p for p in _neighbors(board, point) if board.stone_at(p) == opponent(color)]
    diagonal_mine = [p for p in _diagonals(board, point) if board.stone_at(p) == color]
    if theirs and any(_next_to(a, b) for a in diagonal_mine for b in theirs):
        return HANE
    if theirs and not mine:
        return TSUKE
    if any(board.stone_at(q) == opponent(color) for p in mine for q in _neighbors(board, p)):
        return NOBI
    if diagonal_mine and not mine and not theirs:
        return KOSUMI
    return ""


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
        for p in _neighbors(board, s)
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
    return {board.group_at(p) for p in _neighbors(board, point) if board.stone_at(p) == color}


def _liberty_count(board: Board, group: frozenset[Point]) -> int:
    """Return the liberties that the group of a group's first stone had on another board (the board before)."""
    return len(board.liberties(board.group_at(next(iter(group)))))


def _neighbors(board: Board, point: Point) -> list[Point]:
    """Return the points next to a point (up, down, left, right) on the board."""
    x, y = point
    return [(a, b) for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if _on(board, (a, b))]


def _diagonals(board: Board, point: Point) -> list[Point]:
    """Return the points diagonally next to a point on the board."""
    x, y = point
    return [(a, b) for a, b in ((x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1), (x - 1, y - 1)) if _on(board, (a, b))]


def _next_to(a: Point, b: Point) -> bool:
    """True if two points are next to each other (up, down, left or right)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def _on(board: Board, point: Point) -> bool:
    """True if a point is on the board."""
    return 0 <= point[0] < board.size and 0 <= point[1] < board.size
