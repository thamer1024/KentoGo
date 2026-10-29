"""One answer to a problem, as it is kept in the history.

The moves are kept in the original direction and colors of the problem, even
when the problem was shown rotated or with colors swapped, so that answers to
the same problem can be compared. The losses are kept as numbers, so that the
answers can be judged again later with other judging settings.
"""

from __future__ import annotations

from dataclasses import dataclass

# Where the losses came from.
LOSS_UNKNOWN = ""  # Not judged (yet).
LOSS_FROM_SGF = "sgf"  # The losses are in the SGF file (KaTrain's comments or analysis data).
LOSS_FROM_KATAGO = "katago"  # Both losses were calculated by KataGo (the main model) under the same conditions.
LOSS_FROM_COMPARE = "katago_compare"  # Both losses were calculated by the comparison model.


@dataclass(frozen=True)
class AnswerRecord:
    """One answer to a problem.

    Attributes:
        problem_id: The ID of the problem (see mistakes.problem.problem_id_of).
        answered_at: When the answer was saved (when its result was known, a few seconds after the
            answer at most), in ISO 8601 format with the time zone.
        sgf_path: The SGF file of the problem, for reference.
        move_number: The move number of the problem in the game.
        color: The color that answered, "B" or "W", in the original colors.
        answer: The answer in GTP coordinates, such as "Q16".
        actual_move: The game move in GTP coordinates.
        best_move: KaTrain's best move in GTP coordinates, or "" if it is not known.
        answer_loss: Points lost by the answer, or None if it is not known.
        actual_loss: Points lost by the game move, or None if it is not known.
        loss_source: Where the losses came from: LOSS_UNKNOWN, LOSS_FROM_SGF or LOSS_FROM_KATAGO.
        max_visits: KataGo's number of visits, when the losses came from KataGo.
        correct: The judgment with the settings used then, or None if it was not judged.
        symmetry: How the board was rotated and flipped when it was shown (0 to 7).
        swap_colors: True if the colors were swapped when it was shown.
        record_id: The number of the record in the history, or None before it is saved.
    """

    problem_id: str
    answered_at: str
    sgf_path: str
    move_number: int
    color: str
    answer: str
    actual_move: str
    best_move: str
    answer_loss: float | None
    actual_loss: float | None
    loss_source: str
    max_visits: int | None
    correct: bool | None
    symmetry: int
    swap_colors: bool
    record_id: int | None = None
