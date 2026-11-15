"""The local fight problems: the life and death fights and the boundaries that the user lost in a game.

KentoGo's analysis finds them from KataGo's areas and keeps each one in the node after which it starts (KGA's
"local_fight", see analysis.life_death): the user is to play in the problem's position, and the user's move that
lost the fight is "moves" moves later in the game. In the quiz, the user plays the fight out against KataGo until
the place is settled (not a single move as in a mistake problem).

A local fight problem is a kind of its own: the user's mistake problems (see mistakes.extract) inside a fight (the
user's moves from its position to the move that lost it) are not asked as mistake problems (see lost_moves).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from pysgf import GoNode

from kentogo.common import sgf
from kentogo.common.types import Move, Position, opponent
from kentogo.mistakes.problem import problem_id_of
from kentogo.record.kentogo_analysis import KIND_BOUNDARY, KIND_LIFE_DEATH, read_kentogo_analysis

LINE_EXTRA = 4  # The game's own sequence goes this many moves beyond the move that lost the fight.


@dataclass(frozen=True)
class LocalFight:
    """A local fight that the user lost, asked from where it started.

    Attributes:
        problem_id: An ID made from the position (see local_fight_id); it differs from a mistake problem's.
        sgf_path: Path of the SGF file that the problem came from.
        move_number: The number in the game of the first move to play (the user's).
        position: The position where the fight starts. The user plays next_color.
        kind: KIND_LIFE_DEATH or KIND_BOUNDARY.
        mine: The user's stones that died in the game (GTP points).
        theirs: The opponent's stones that lived in the game (the user did not kill them).
        points: The empty points of the user that the user lost.
        moves: How many moves of the game there are from the position to the user's move that lost the fight,
            that move included.
        score_lead: Black's score lead in the position by KentoGo's analysis, or None if unknown.
        game_line: The moves played in the game from the position, LINE_EXTRA beyond the move that lost the fight.
    """

    problem_id: str
    sgf_path: str
    move_number: int
    position: Position
    kind: str
    mine: tuple[str, ...]
    theirs: tuple[str, ...]
    points: tuple[str, ...]
    moves: int
    score_lead: float | None
    game_line: tuple[Move, ...]

    @property
    def lost_move_number(self) -> int:
        """Return the number in the game of the user's move that lost the fight."""
        return self.move_number - 1 + self.moves

    def mistake_ids(self) -> set[str]:
        """Return the IDs that the mistake problems of the user's moves inside the fight have (or had).

        Those mistake problems are not made any more (see lost_moves); their answers kept in the history must not
        bring them back as reviews.
        """
        color = self.position.next_color
        moves = self.position.moves
        ids = set()
        for move in self.game_line[: self.moves]:
            if move.color == color:
                ids.add(problem_id_of(replace(self.position, moves=moves)))
            moves = (*moves, move)
        return ids


def local_fight_id(position: Position) -> str:
    """Make the ID of a local fight problem from its position (16 hexadecimal letters).

    It depends only on the position, as a mistake problem's ID (mistakes.problem.problem_id_of), but is made
    with another prefix, so that a fight and a mistake in the same position have different IDs (and histories).
    """
    parts = ["local_fight", str(position.size)]
    parts += sorted(f"A{stone.color}{stone.gtp()}" for stone in position.setup)
    parts += [f"{move.color}{move.gtp()}" for move in position.moves]
    return hashlib.sha1(";".join(parts).encode("ascii")).hexdigest()[:16]


def find_local_fights(main_line: list[GoNode], start: Position, sgf_path: str, my_color: str) -> tuple[LocalFight, ...]:
    """Return the local fights that KentoGo's analysis kept in the main line of a game, in the order played.

    A fight is used only when the user is to play in its position (the user's color may have been found otherwise
    when the game was analyzed).

    Args:
        main_line: The nodes of the main line, the root first.
        start: The position at the start of the game (its moves are not used).
        sgf_path: Path of the SGF file.
        my_color: The user's color.
    """
    fights = []
    played: list[Move] = []
    for index, node in enumerate(main_line):
        move = sgf.node_move(node)
        if move is not None:
            played.append(move)
        data = (read_kentogo_analysis(node) or {}).get("local_fight")
        next_color = opponent(move.color) if move is not None else my_color
        if isinstance(data, dict) and next_color == my_color:
            position = Position(start.size, start.komi, start.rules, start.setup, tuple(played), my_color)
            fight = _fight(data, node, position, sgf_path, main_line[index + 1 :])
            if fight is not None:
                fights.append(fight)
    return tuple(fights)


def lost_moves(fights: tuple[LocalFight, ...]) -> set[int]:
    """Return the numbers in the game of the user's moves inside the fights (they are not mistake problems)."""
    return {number for fight in fights for number in range(fight.move_number, fight.lost_move_number + 1)}


def _fight(data: dict, node: GoNode, position: Position, sgf_path: str, after: list[GoNode]) -> LocalFight | None:
    """Make a local fight from KGA's data of the node where it starts, or None when the data is not complete."""
    try:
        kind, moves = str(data["kind"]), int(data["moves"])
        mine, theirs, points = (
            tuple(str(point) for point in data.get(key, ())) for key in ("mine", "theirs", "points")
        )
    except (KeyError, TypeError, ValueError):
        return None
    if kind not in (KIND_LIFE_DEATH, KIND_BOUNDARY) or moves < 1:
        return None
    analysis = read_kentogo_analysis(node) or {}
    lead = (analysis.get("root") or {}).get("scoreLead")
    line = [move for item in after[: moves + LINE_EXTRA] if (move := sgf.node_move(item)) is not None]
    return LocalFight(
        problem_id=local_fight_id(position),
        sgf_path=sgf_path,
        move_number=len(position.moves) + 1,
        position=position,
        kind=kind,
        mine=mine,
        theirs=theirs,
        points=points,
        moves=moves,
        score_lead=float(lead) if isinstance(lead, int | float) else None,
        game_line=tuple(line),
    )
