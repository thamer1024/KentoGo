"""Which of the user's mistakes in a game become problems, and are given to the AI.

The user's moves that KaTrain evaluated are chosen in two rounds, until there are as many
as the quiz makes problems from one game (see Selection):

1. Moves that lost at least the smallest loss of the quiz, played while the game was still
   open: not when, before the move, one side's winrate was at least the decided winrate, or
   the score lead was more than the decided lead (settings of the quiz; from KaTrain's
   analysis data, and a move without it counts as open). Of the moves with the same best move, only the one that lost the most
   is chosen, so that the AI does not explain the same point again and again. The biggest
   losses first.
2. If there are not enough, the other moves (in decided positions, with a best move already
   chosen, or with a smaller loss), the biggest losses first.

The chosen moves are returned in the order they were played. The quiz (mistakes.extract) and
the AI commentary (commentary.material) both choose in this way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kentogo.mistakes.extract import ExtractSettings

DECIDED_WINRATE = 99.0  # A position where one side's winrate (in percent) is at least this is decided.
DECIDED_LEAD = 40.0  # A position where one side leads by more than this many points is decided.


@dataclass(frozen=True)
class Selection:
    """How many moves are chosen, and which moves come in the first round.

    Attributes:
        count: How many moves are chosen (the number of problems per game of the quiz).
        min_loss: The smallest loss of a move in the first round (the smallest loss of the quiz).
        decided_winrate: A position where one side's winrate (in percent) is at least this is decided.
        decided_lead: A position where one side leads by more than this many points is decided.
    """

    count: int = 5
    min_loss: float = 3.0
    decided_winrate: float = DECIDED_WINRATE
    decided_lead: float = DECIDED_LEAD

    @classmethod
    def from_quiz(cls, settings: ExtractSettings) -> Selection:
        """Return the selection that matches the problems that the quiz makes from one game."""
        return cls(
            settings.problems_per_game, settings.min_points_lost, settings.decided_winrate, settings.decided_lead
        )

    def is_decided(self, winrate: float | None, score_lead: float | None) -> bool:
        """Return True if a position is decided, from black's winrate (0 to 1) and black's score lead.

        A value that is not known (None) does not make the position decided.
        """
        by_winrate = winrate is not None and max(winrate, 1 - winrate) * 100 >= self.decided_winrate
        by_lead = score_lead is not None and abs(score_lead) > self.decided_lead
        return by_winrate or by_lead


@dataclass(frozen=True)
class MoveChoice:
    """One of the user's moves that can be chosen.

    Attributes:
        number: The move number (or another number that tells the moves apart).
        loss: The points it lost.
        best_move: KaTrain's best move instead of it (GTP), or None if not known.
        decided: True if the game was already decided before the move (see Selection.is_decided).
    """

    number: int
    loss: float
    best_move: str | None = None
    decided: bool = False


def choose_moves(moves: list[MoveChoice], selection: Selection) -> list[int]:
    """Choose the moves to explain (see the module docstring).

    Args:
        moves: The user's moves that KaTrain evaluated.
        selection: How many to choose, and the smallest loss of the first round.

    Returns:
        The numbers of the chosen moves, in the order they were played.
    """
    by_loss = sorted(moves, key=lambda move: (-move.loss, move.number))
    chosen = _first_round(by_loss, selection)
    chosen += [move for move in by_loss if move not in chosen][: selection.count - len(chosen)]
    return sorted(move.number for move in chosen)


def _first_round(by_loss: list[MoveChoice], selection: Selection) -> list[MoveChoice]:
    """Choose big enough open moves, one for each best move, the biggest losses first."""
    chosen: list[MoveChoice] = []
    best_moves: set[str] = set()
    for move in by_loss:
        if len(chosen) == selection.count or move.loss < selection.min_loss:
            break
        if move.decided or (move.best_move is not None and move.best_move in best_moves):
            continue
        chosen.append(move)
        if move.best_move is not None:
            best_moves.add(move.best_move)
    return chosen
