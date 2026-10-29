"""The paste mode: the user gives the prompt to any AI in its chat screen, and pastes the answer back.

One game at a time:

1. prepare_paste: make the prompt. The screen shows it with a copy button, and a field for the answer.
   If KaTrain has not analyzed the game, NotAnalyzedError is raised: the screen asks the user to
   analyze it in KaTrain, and remember_not_analyzed makes the game pending.
2. apply_paste: when the user pastes the answer, it is checked. With errors, nothing is written,
   and the problems are returned so that the user can paste again. Without errors, it is
   written into the SGF file.

If the user cancels, the screen simply does not call apply_paste: nothing is written or remembered.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.commentary.answer import Answer
from kentogo.commentary.history import CommentaryHistory
from kentogo.commentary.job import GameRequest, PreparedGame, check_answer, finish_game, prepare_game
from kentogo.commentary.prompt_text import PromptText
from kentogo.commentary.sgf_writer import WriteResult
from kentogo.mistakes.extract import ExtractSettings


@dataclass(frozen=True)
class PasteResult:
    """What happened to a pasted answer.

    Attributes:
        answer: The checked answer (with its problems).
        written: What was written, or None if nothing was written (the answer has errors, or writing failed).
        error: Why writing failed ("" if it did not fail).
    """

    answer: Answer
    written: WriteResult | None = None
    error: str = ""


def prepare_paste(
    request: GameRequest, text: PromptText, conditions: ExtractSettings = ExtractSettings()
) -> PreparedGame:
    """Make the prompt for a game. The text to copy is prepared.prompt.for_paste().

    conditions are the quiz's conditions for choosing problems (see commentary.material).

    Raises:
        NotAnalyzedError: If KaTrain has not analyzed the game.
        OSError, ValueError: If the file cannot be read.
    """
    return prepare_game(request, text, conditions)


def apply_paste(prepared: PreparedGame, answer_text: str, history: CommentaryHistory | None) -> PasteResult:
    """Check a pasted answer, and write it into the SGF file if it has no errors."""
    answer = check_answer(prepared, answer_text)
    if not answer.ok:
        return PasteResult(answer)
    try:
        return PasteResult(answer, finish_game(prepared, answer, history))
    except (OSError, ValueError) as error:
        return PasteResult(answer, error=str(error))


def remember_not_analyzed(request: GameRequest, history: CommentaryHistory | None) -> None:
    """Remember the user's inputs for a game that KaTrain has not analyzed, and make it pending."""
    if history is None:
        return
    history.save_inputs(request.name, request.my_color, request.my_rank, request.relation)
    history.mark_pending(request.name)
