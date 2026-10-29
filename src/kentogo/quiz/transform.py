"""Rotate, flip and swap colors of a problem, so that the user does not just remember the answer.

There are 8 ways to rotate and flip a square board (symmetry 0 to 7):
symmetry 0 changes nothing, 1 to 3 rotate by 90, 180 and 270 degrees,
and 4 to 7 flip the board left to right first and then rotate in the same way.
Colors can also be swapped (black stones become white, and white become black).

The user answers on the changed board. The answer is changed back with
inverse() before it is compared with the original problem. The board stays
changed after the answer, and the notes are rewritten for it (see notes_transform).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from kentogo.common.types import Move, Position, opponent
from kentogo.katago.estimate import Estimate, Standing
from kentogo.mistakes.problem import Problem

SYMMETRIES = range(8)


@dataclass(frozen=True)
class BoardTransform:
    """One way to change a problem.

    Attributes:
        symmetry: How to rotate and flip the board, from 0 to 7.
        swap_colors: True to swap black and white.
    """

    symmetry: int = 0
    swap_colors: bool = False

    def point(self, coord: tuple[int, int] | None, size: int) -> tuple[int, int] | None:
        """Change a point on a board of the given size. None (a pass) stays None."""
        if coord is None:
            return None
        x, y = coord
        if self.symmetry >= 4:
            x = size - 1 - x  # Flip left to right.
        for _ in range(self.symmetry % 4):
            x, y = y, size - 1 - x  # Rotate by 90 degrees.
        return x, y

    def move(self, move: Move, size: int) -> Move:
        """Change the point and, if needed, the color of a move."""
        color = opponent(move.color) if self.swap_colors else move.color
        return Move(color, self.point(move.coord, size))

    def moves(self, moves: tuple[Move, ...], size: int) -> tuple[Move, ...]:
        """Change all moves in a sequence."""
        return tuple(self.move(move, size) for move in moves)

    def position(self, position: Position) -> Position:
        """Change the stones, the moves and the player to move of a position."""
        size = position.size
        return replace(
            position,
            setup=self.moves(position.setup, size),
            moves=self.moves(position.moves, size),
            next_color=opponent(position.next_color) if self.swap_colors else position.next_color,
        )

    def problem(self, problem: Problem) -> Problem:
        """Change a problem: its position, moves and sequences. The problem ID stays the same.

        The notes are not changed here: notes_transform.transform_notes rewrites them.
        """
        size = problem.position.size
        return replace(
            problem,
            position=self.position(problem.position),
            actual_move=self.move(problem.actual_move, size),
            best_move=self.move(problem.best_move, size) if problem.best_move else None,
            variations=tuple(replace(v, moves=self.moves(v.moves, size)) for v in problem.variations),
        )

    def standing(self, standing: Standing, size: int) -> Standing:
        """Change the territory and the standing (see katago.estimate): the owners move, and swap sides with the colors."""
        sign = -1.0 if self.swap_colors else 1.0
        color = opponent(standing.color) if self.swap_colors else standing.color
        return Standing(self._estimate(standing.end, size, sign), self._estimate(standing.game, size, sign), color)

    def _estimate(self, estimate: Estimate, size: int, sign: float) -> Estimate:
        """Change one view of KataGo: move the owners, and give the lead and the owners the sign of the colors."""
        ownership = {self.point(point, size): value * sign for point, value in estimate.ownership.items()}
        return Estimate(estimate.lead * sign, ownership)

    def inverse(self) -> BoardTransform:
        """Return the change that brings the board back to the original.

        A flip followed by a rotation brings itself back when it is done twice,
        so symmetries 4 to 7 are their own inverse. A rotation by r turns is
        undone by a rotation by 4 - r turns.
        """
        symmetry = self.symmetry if self.symmetry >= 4 else (4 - self.symmetry) % 4
        return BoardTransform(symmetry, self.swap_colors)


IDENTITY = BoardTransform()


def random_transform(rng: random.Random, rotate: bool = True, swap_colors: bool = False) -> BoardTransform:
    """Choose a change at random.

    Args:
        rng: The random number generator. Tests pass one with a fixed seed.
        rotate: Choose one of the 8 rotations and flips. If False, the board is not rotated.
        swap_colors: Swap colors in half of the cases. If False, colors are never swapped.

    Returns:
        The chosen change.
    """
    symmetry = rng.choice(SYMMETRIES) if rotate else 0
    swap = rng.random() < 0.5 if swap_colors else False
    return BoardTransform(symmetry, swap)
