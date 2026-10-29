"""The score of an answer: how many of the points lost in the game the answer gets back.

Example: the move in the game lost 10 points, and the answer loses 1 point.
The answer is 9 points better, and it gets back 90% of the loss.

The losses of the game move and of the answer must be calculated under the
same conditions (the same model and settings), or they cannot be compared.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Comparison:
    """The answer compared with the move played in the game.

    Attributes:
        actual_loss: Points lost by the move in the game.
        answer_loss: Points lost by the answer.
        improvement: How many points better the answer is (actual_loss - answer_loss).
            It is negative if the answer is worse.
        recovered_ratio: The part of the loss that the answer gets back, from 0.0 to 1.0.
    """

    actual_loss: float
    answer_loss: float
    improvement: float
    recovered_ratio: float


def score_answer(actual_loss: float, answer_loss: float) -> float:
    """Return the part of the loss that the answer gets back.

    Args:
        actual_loss: Points lost by the move in the game.
        answer_loss: Points lost by the answer. A negative value (the answer looks
            a little better than the best move, because of noise in the analysis)
            counts as 0.

    Returns:
        1.0 for the best move, 0.0 if the answer is not better than the game move,
        and a value in between otherwise.
    """
    answer_loss = max(answer_loss, 0.0)
    if actual_loss <= 0:
        return 1.0 if answer_loss <= 0 else 0.0
    ratio = (actual_loss - answer_loss) / actual_loss
    return min(max(ratio, 0.0), 1.0)


def compare_with_actual(actual_loss: float, answer_loss: float) -> Comparison:
    """Compare the answer with the move played in the game.

    Args:
        actual_loss: Points lost by the move in the game.
        answer_loss: Points lost by the answer, calculated under the same conditions.

    Returns:
        The comparison.
    """
    return Comparison(
        actual_loss=actual_loss,
        answer_loss=answer_loss,
        improvement=actual_loss - answer_loss,
        recovered_ratio=score_answer(actual_loss, answer_loss),
    )
