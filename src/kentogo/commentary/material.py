"""The material for the AI commentary: the facts about the user's biggest mistakes in a game.

Everything here is worked out by KentoGo from the SGF file (KaTrain's comments and
analysis data) and from the rules of the board, so that the AI does not have to work
it out itself, which is where an AI makes most of its mistakes:

- The moves: the moves that the quiz makes problems from, with the quiz's conditions
  (mistakes.extract: the number of problems per game, the smallest loss, the opening moves left
  out, the decided positions, one move for each best move, and the moves that KaTrain took
  back in a teaching game when that setting is on), in the order of their numbers. So the
  AI explains the problems of the quiz. A move taken back is in a branch next to the move
  of the game with the same number; it has no reply of the opponent.
- For each move: the board before it, the best move and KaTrain's predicted sequence,
  what happens on the board when the sequence is played (captured stones, stones in
  atari, the board at the end), the groups near the move with their liberties, the
  candidate moves with their losses (from KaTrain's analysis data, when it is there),
  the score after the move, and the opponent's reply.
- For the game: how many of the user's moves lost at least each size of points.

How the material is written for the AI is decided by commentary.prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from pysgf import GoNode

from kentogo.common import sgf
from kentogo.common.board import Board, IllegalMoveError, Point
from kentogo.common.types import Move, Position, moves_from_gtp, opponent
from kentogo.mistakes.extract import ExtractSettings, extract_problems
from kentogo.record.game_record import BoardState, GameRecord, MoveRecord, read_game_record, read_move_record
from kentogo.record.katrain_kt import SUPPORTED_VERSION, candidate_losses, decode_kt

# The sizes of losses that are counted for the whole game (the same as the user's script).
LOSS_SIZES = (20, 12, 10, 8, 6, 3)
CANDIDATES_PER_MOVE = 5  # How many candidate moves are given for each move.
NEARBY_DISTANCE = 3  # Groups with a stone this close to the move or the best move are described.
NEARBY_GROUPS = 8  # At most this many groups are described, the closest first.


@dataclass(frozen=True)
class GroupInfo:
    """A group of stones near a move.

    Attributes:
        color: "B" or "W".
        stones: The points of the stones, sorted.
        liberties: The number of liberties.
    """

    color: str
    stones: tuple[Point, ...]
    liberties: int


@dataclass(frozen=True)
class PvStep:
    """One move of a predicted sequence, played on the board.

    Attributes:
        move: The move.
        captured: The stones that the move took (sorted).
        in_atari: The groups that the move put in atari (one liberty left, and not in atari before it).
    """

    move: Move
    captured: tuple[Point, ...]
    in_atari: tuple[GroupInfo, ...]


@dataclass(frozen=True)
class OpponentReply:
    """The move that the opponent played after the user's move, with KaTrain's evaluation of it.

    Attributes:
        move: The opponent's move.
        points_lost: Its loss, or None if KaTrain did not write one.
        best_move: The opponent's best move (GTP), or None.
        pv: KaTrain's predicted sequence for the opponent (moves).
    """

    move: Move
    points_lost: float | None
    best_move: str | None
    pv: tuple[Move, ...]


@dataclass(frozen=True)
class MoveMaterial:
    """The facts about one of the user's mistakes.

    Attributes:
        number: The move number.
        played: The user's move.
        points_lost: The loss of the move.
        best_move: The best move, or None if KaTrain did not write it.
        before: The board before the move.
        last_move: The move before it (the opponent's), or None at the start.
        pv: KaTrain's predicted sequence from the position before the move (it starts with the best move).
        pv_steps: The predicted sequence played on the board (it stops at a move that cannot be played).
        after_pv: The board after the predicted sequence.
        nearby: The groups near the played move and the best move, on the board before the move.
        candidates: Candidate moves (GTP) with their losses, the smallest loss first (empty without analysis data).
        score_after: The score after the move, from black's side (None without analysis data).
        reply: The opponent's next move, or None if the game ended.
        notes: The user's notes on the move ("" if there are none).
        katrain_text: The text that KaTrain wrote for the move, as it is (score, policy rank, and so on).
        taken_back: True if KaTrain took the move back in a teaching game (it is in a branch, not in the game).
    """

    number: int
    played: Move
    points_lost: float
    best_move: Move | None
    before: BoardState
    last_move: Move | None
    pv: tuple[Move, ...]
    pv_steps: tuple[PvStep, ...]
    after_pv: BoardState
    nearby: tuple[GroupInfo, ...]
    candidates: tuple[tuple[str, float], ...]
    score_after: float | None
    reply: OpponentReply | None
    notes: str
    katrain_text: str
    taken_back: bool = False


@dataclass(frozen=True)
class GameMaterial:
    """The facts about the user's mistakes in one game.

    Attributes:
        size: The size of the board.
        komi: The komi.
        my_color: The user's color, "B" or "W".
        moves: The mistakes to explain, in the order they were played.
        loss_counts: For each size in LOSS_SIZES, how many of the user's moves lost at least that many points.
        final_number: The number of the last move of the game.
    """

    size: int
    komi: float
    my_color: str
    moves: tuple[MoveMaterial, ...]
    loss_counts: tuple[tuple[int, int], ...]
    final_number: int


def has_katrain_evaluation(record: GameRecord, my_color: str) -> bool:
    """Return True if KaTrain has written the loss of any of the user's moves (the game was analyzed)."""
    return bool(_user_losses(record, my_color))


def make_material(root: GoNode, my_color: str, conditions: ExtractSettings = ExtractSettings()) -> GameMaterial:
    """Make the material for the AI commentary of a game.

    Args:
        root: The root node of the game.
        my_color: The user's color, "B" or "W".
        conditions: The quiz's conditions for choosing problems (see the module docstring).

    Returns:
        The material. It has no moves if KaTrain has not analyzed the game.
    """
    record = read_game_record(root)
    nodes = _move_nodes(root)
    version = str(root.get_property("KTV", SUPPORTED_VERSION))
    losses = _user_losses(record, my_color)
    chosen = quiz_nodes(root, nodes, my_color, conditions)
    moves = tuple(
        _move_material(record, node, number, version, node is not _game_node(nodes, number)) for number, node in chosen
    )
    counts = tuple((size, sum(1 for loss in losses.values() if loss >= size)) for size in LOSS_SIZES)
    return GameMaterial(record.size, record.komi, my_color, moves, counts, record.last_position)


def _user_losses(record: GameRecord, my_color: str) -> dict[int, float]:
    """Return the loss of each of the user's moves that KaTrain evaluated, by move number."""
    losses = {}
    for move in record.moves:
        info = move.katrain
        if move.move.color != my_color or info is None or info.points_lost is None:
            continue
        if (info.color, info.move) == (move.move.color, move.move.gtp()):  # Otherwise the comment is not trusted.
            losses[move.number] = info.points_lost
    return losses


def quiz_nodes(
    root: GoNode, nodes: list[GoNode], my_color: str, conditions: ExtractSettings
) -> list[tuple[int, GoNode]]:
    """Return the moves that the quiz makes problems from, as (move number, node), in the order of the numbers.

    The quiz is asked with the user's color, so that it does not have to find it. The node of a
    problem is the move of the game with its number, or a branch next to it (a move taken back).

    Args:
        root: The root node of the game.
        nodes: The nodes of the game that have a move (see _move_nodes).
        my_color: The user's color.
        conditions: The quiz's conditions for choosing problems.
    """
    found = []
    for problem in extract_problems(root, "", conditions, recorded_color=my_color).problems:
        node = problem_node(nodes, problem.move_number, problem.actual_move)
        if node is not None:
            found.append((problem.move_number, node))
    return sorted(found, key=lambda item: item[0])


def problem_node(nodes: list[GoNode], number: int, move: Move) -> GoNode | None:
    """Return the node of a move with a number: the move of the game, or a branch in its place (None if none)."""
    parent = position_node(nodes, number)
    if parent is None:
        return None
    game_node = _game_node(nodes, number)
    if game_node is not None and sgf.node_move(game_node) == move:
        return game_node
    return next((child for child in parent.children if sgf.node_move(child) == move), None)


def position_node(nodes: list[GoNode], number: int) -> GoNode | None:
    """Return the node of the game before the move with a number (the parent of that move and its branches)."""
    if number >= 2:
        return nodes[number - 2] if number - 2 < len(nodes) else None
    return nodes[0].parent if nodes else None


def _game_node(nodes: list[GoNode], number: int) -> GoNode | None:
    """Return the node of the move of the game with a number, or None after the end of the game."""
    return nodes[number - 1] if 1 <= number <= len(nodes) else None


def _move_nodes(root: GoNode) -> list[GoNode]:
    """Return the nodes of the main line that have a move, so that node i-1 is move i (as in GameRecord)."""
    return [node for node in sgf.main_line(root)[1:] if sgf.node_move(node) is not None]


def _move_material(record: GameRecord, node: GoNode, number: int, version: str, taken_back: bool) -> MoveMaterial:
    """Make the facts about one mistake (number is its move number, and node its node: in the game or a branch)."""
    move = read_move_record(node, number)
    info = move.katrain
    before = record.state(number - 1)
    board = _board(record, before)
    best = Move.from_gtp(info.best_move, move.move.color) if info.best_move else None
    pv = moves_from_gtp(info.pv, info.pv_color) if info.pv and info.pv_color else ()
    steps, after = _play_sequence(board, pv)
    previous = record.move_at(number - 1)
    return MoveMaterial(
        number=number,
        played=move.move,
        points_lost=info.points_lost,
        best_move=best,
        before=before,
        last_move=previous.move if previous else None,
        pv=pv,
        pv_steps=steps,
        after_pv=after,
        nearby=_nearby_groups(board, [move.move, best]),
        candidates=_candidates(node.parent, move.move.color, version),
        score_after=_score(node, version),
        reply=None if taken_back else _reply(record, number),
        notes=move.notes,
        katrain_text=move.katrain_text,
        taken_back=taken_back,
    )


def _board(record: GameRecord, state: BoardState) -> Board:
    """Make a board with the stones of a state, to play moves on it."""
    stones = tuple(Move(color, point) for point, color in sorted(state.stones.items()))
    board = Board.from_position(Position(record.size, record.komi, record.rules, stones, (), "B"))
    board.captures = dict(state.captures)
    return board


def _play_sequence(board: Board, moves: tuple[Move, ...]) -> tuple[tuple[PvStep, ...], BoardState]:
    """Play a sequence on a copy of the board, and say what each move does.

    The sequence stops at a move that cannot be played (it should not happen).

    Returns:
        The steps, and the board at the end.
    """
    board = board.copy()
    steps = []
    for move in moves:
        atari_before = {group.stones for group in _groups_in_atari(board)}
        try:
            captured = board.play(move)
        except IllegalMoveError:
            break
        new_atari = tuple(group for group in _groups_in_atari(board) if group.stones not in atari_before)
        steps.append(PvStep(move, tuple(sorted(captured)), new_atari))
    return tuple(steps), BoardState(board.stones(), dict(board.captures))


def _groups_in_atari(board: Board) -> tuple[GroupInfo, ...]:
    """Return all groups on the board that have only one liberty."""
    return tuple(group for group in _all_groups(board) if group.liberties == 1)


def _nearby_groups(board: Board, moves: list[Move | None]) -> tuple[GroupInfo, ...]:
    """Return the groups that have a stone within NEARBY_DISTANCE of any of the moves (passes are ignored).

    At most NEARBY_GROUPS groups are returned: the closest ones, in the order of their first stone.
    """
    centers = [move.coord for move in moves if move is not None and move.coord is not None]

    def distance(group: GroupInfo) -> int:
        return min((max(abs(x - cx), abs(y - cy)) for x, y in group.stones for cx, cy in centers), default=99)

    groups = [group for group in _all_groups(board) if distance(group) <= NEARBY_DISTANCE]
    closest = sorted(groups, key=distance)[:NEARBY_GROUPS]
    return tuple(group for group in groups if group in closest)


def _all_groups(board: Board) -> list[GroupInfo]:
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


def _candidates(parent: GoNode | None, color: str, version: str) -> tuple[tuple[str, float], ...]:
    """Return the candidate moves before a move with their losses, the smallest loss first."""
    analysis = _analysis(parent, version)
    losses = candidate_losses(analysis, color) if analysis else {}
    ordered = sorted(losses.items(), key=lambda item: (item[1], item[0]))
    return tuple(ordered[:CANDIDATES_PER_MOVE])


def _score(node: GoNode, version: str) -> float | None:
    """Return the score after a node's move, from black's side, or None without analysis data."""
    root = (_analysis(node, version) or {}).get("root") or {}
    score = root.get("scoreLead") if isinstance(root, dict) else None
    return float(score) if isinstance(score, int | float) else None


def _analysis(node: GoNode | None, version: str) -> dict | None:
    """Return KaTrain's main analysis of a node, or None if there is none or it cannot be read."""
    values = node.get_list_property("KT") if node is not None else None
    if not values:
        return None
    try:
        return decode_kt(values, version)
    except ValueError:
        return None


def _reply(record: GameRecord, number: int) -> OpponentReply | None:
    """Return the opponent's move after move `number`, or None if there is none."""
    reply = record.move_at(number + 1)
    if reply is None or reply.move.color != opponent(record.moves[number - 1].move.color):
        return None
    return _opponent_reply(reply)


def _opponent_reply(reply: MoveRecord) -> OpponentReply:
    """Make the opponent's reply from its record."""
    info = reply.katrain
    if info is None:
        return OpponentReply(reply.move, None, None, ())
    pv = moves_from_gtp(info.pv, info.pv_color) if info.pv and info.pv_color else ()
    return OpponentReply(reply.move, info.points_lost, info.best_move, pv)
