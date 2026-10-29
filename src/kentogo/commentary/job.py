"""The steps for the AI commentary of one game, shared by the API mode (commentary.batch) and the paste mode.

1. prepare_game: read the game and make the material and the prompt.
2. (The AI answers: through its API, or the user pastes the answer.)
3. finish_game: check the answer and write it into the SGF file, and remember the game as done.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kentogo.commentary.answer import Answer, read_answer
from kentogo.commentary.history import CommentaryHistory
from kentogo.commentary.language import JAPANESE, CommentaryLanguage
from kentogo.commentary.material import GameMaterial, has_katrain_evaluation, make_material
from kentogo.commentary.prompt import PlayerInfo, Prompt, build_prompt
from kentogo.commentary.prompt_text import PromptText
from kentogo.commentary.sgf_writer import WriteResult, write_commentary
from kentogo.common import sgf
from kentogo.mistakes.extract import ExtractSettings
from kentogo.record.game_record import read_game_record


@dataclass(frozen=True)
class GameRequest:
    """What the user gave for one game.

    Attributes:
        path: The SGF file.
        my_color: "B" or "W".
        my_rank: The user's rank at the time of the game ("" if not given).
        relation: The rank of the opponent compared with the user (see prompt.RELATIONS).
    """

    path: Path
    my_color: str
    my_rank: str = ""
    relation: str = ""

    @property
    def name(self) -> str:
        """The name of the SGF file (how the history knows the game)."""
        return self.path.name


@dataclass(frozen=True)
class PreparedGame:
    """A game ready to be given to an AI.

    Attributes:
        request: What the user gave.
        material: The facts about the user's mistakes.
        prompt: The prompt.
        language: The language of the commentary (of the prompt, and of the words written with the answer).
    """

    request: GameRequest
    material: GameMaterial
    prompt: Prompt
    language: CommentaryLanguage = JAPANESE

    @property
    def asked_moves(self) -> list[int]:
        """The numbers of the moves that the AI is asked to explain."""
        return [move.number for move in self.material.moves]


class NotAnalyzedError(Exception):
    """KaTrain has not analyzed the game (none of the user's moves has KaTrain's loss)."""


class NothingToExplainError(Exception):
    """KaTrain has analyzed the game, but none of the user's moves becomes a problem of the quiz."""


def prepare_game(
    request: GameRequest, text: PromptText, conditions: ExtractSettings = ExtractSettings()
) -> PreparedGame:
    """Read a game, and make the material and the prompt.

    Args:
        request: The game and the user's inputs.
        text: The parts of the prompt that the user can change, with the language of the commentary.
        conditions: The quiz's conditions for choosing problems: the moves that become problems are explained.

    Raises:
        NotAnalyzedError: If KaTrain has not analyzed the game.
        NothingToExplainError: If no move of the user meets the quiz's conditions.
        OSError, ValueError: If the file cannot be read.
    """
    root = sgf.load_game(request.path)
    material = make_material(root, request.my_color, conditions)
    if not material.moves:
        if has_katrain_evaluation(read_game_record(root), request.my_color):
            raise NothingToExplainError(request.name)
        raise NotAnalyzedError(request.name)
    prompt = build_prompt(material, PlayerInfo(request.my_rank, request.relation), text)
    return PreparedGame(request, material, prompt, text.language)


def check_answer(prepared: PreparedGame, answer_text: str) -> Answer:
    """Read and check the AI's answer for a prepared game."""
    return read_answer(answer_text, prepared.asked_moves)


def finish_game(prepared: PreparedGame, answer: Answer, history: CommentaryHistory | None) -> WriteResult:
    """Write a checked answer into the SGF file, and remember the game as done with the user's inputs.

    Args:
        prepared: The prepared game.
        answer: The checked answer (answer.ok must be True).
        history: Where the game is remembered, or None if it cannot be used.

    Returns:
        What was written.

    Raises:
        ValueError: If the answer has errors, or the file was changed since it was prepared.
        OSError: If the file cannot be written.
    """
    request = prepared.request
    result = write_commentary(request.path, prepared.material, answer, request.my_rank, prepared.language.labels)
    if history is not None:
        history.save_inputs(request.name, request.my_color, request.my_rank, request.relation)
        history.mark_done(request.name, request.path.stat().st_mtime_ns)
    return result
