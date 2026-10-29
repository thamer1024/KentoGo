"""The data of a problem: the position just before a big mistake.

A problem keeps everything that is needed to ask it and to show the answer
afterwards, so the quiz does not need to read the SGF file again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from kentogo.common.types import Move, Position

# Where a sequence came from (Variation.source).
SOURCE_KATRAIN = "katrain"  # KaTrain's best sequence, read from the game file (see extract).
SOURCE_KATAGO_ANSWER = "katago"  # KataGo's sequence after the answer.
SOURCE_KATAGO_ACTUAL = "katago_actual"  # KataGo's sequence after the game move.
SOURCE_KATAGO_COMPARE = "katago_compare"  # The comparison model's best sequence in the position.


@dataclass(frozen=True)
class Variation:
    """A sequence of moves to show on the board after the user answers.

    Attributes:
        moves: The moves, starting from the problem position.
        source: Where the sequence came from, such as "katrain".
            Later, sequences from KataGo will have other names.
        comment: A short text to show with the sequence.
    """

    moves: tuple[Move, ...]
    source: str
    comment: str = ""


@dataclass(frozen=True)
class Problem:
    """A problem made from a big mistake in a game.

    Attributes:
        problem_id: An ID made from the position (see problem_id_of).
        sgf_path: Path of the SGF file that the problem came from.
        move_number: The number of the mistake in the game.
        position: The position just before the mistake. The user plays next_color.
        actual_move: The move played in the game (the mistake).
        best_move: The best move according to KaTrain, or None if unknown.
        points_lost: Points lost by the actual move, according to KaTrain.
        variations: Sequences to show after the user answers.
        notes: The user's notes on the mistake.
            They are shown only after the user answers.
        candidate_losses: The loss of each move that KaTrain analyzed in the problem position,
            as (GTP point, points lost) pairs, from KaTrain's analysis data (KT). Empty if the
            game has no analysis data. An answer that is one of these is judged without KataGo.
        ai_comment: The AI commentary on the mistake (see record.ai_comment), or "" if there is none.
    """

    problem_id: str
    sgf_path: str
    move_number: int
    position: Position
    actual_move: Move
    best_move: Move | None
    points_lost: float
    variations: tuple[Variation, ...] = ()
    notes: str = ""
    candidate_losses: tuple[tuple[str, float], ...] = ()
    ai_comment: str = ""


def problem_id_of(position: Position) -> str:
    """Make the ID of a problem from its position.

    The ID depends only on the board size, the setup stones, and the moves
    from the start. So the same position gets the same ID even if the file is
    renamed or analyzed again.

    Args:
        position: The problem position.

    Returns:
        16 hexadecimal letters.
    """
    parts = [str(position.size)]
    parts += sorted(f"A{stone.color}{stone.gtp()}" for stone in position.setup)
    parts += [f"{move.color}{move.gtp()}" for move in position.moves]
    return hashlib.sha1(";".join(parts).encode("ascii")).hexdigest()[:16]
