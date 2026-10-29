"""Give several games to an AI through its API, one after another, and write the answers into the SGF files.

The screen collects the inputs of the games (see commentary.candidates), then calls
run_listed_games (or run_batch for games not from the list), usually in a background thread. run_batch tells the screen what happens through a
BatchListener, and stops after the current game when `cancel` is set (the current game is
not written then).

The history is kept up to date, so that the list is right the next time:

- A game that gets its commentary is remembered as done.
- A game that KaTrain has not analyzed, that failed, or that was not reached because of
  cancel, is remembered as pending, so that it is shown again.
- With run_listed_games, at the end, the time of the start of the run becomes the time from
  which changed games are shown.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kentogo.commentary.answer import AnswerProblem
from kentogo.commentary.history import CommentaryHistory
from kentogo.commentary.job import (
    GameRequest,
    NotAnalyzedError,
    NothingToExplainError,
    check_answer,
    finish_game,
    prepare_game,
)
from kentogo.commentary.prompt_text import PromptText
from kentogo.commentary.provider_base import Generation, Provider, ProviderError
from kentogo.mistakes.extract import ExtractSettings

STATUS_DONE = "done"  # The commentary was written.
STATUS_NOT_ANALYZED = "not_analyzed"  # KaTrain has not analyzed the game.
STATUS_NOTHING = "nothing"  # No move of the user meets the quiz's conditions, so there is nothing to explain.
STATUS_FAILED = "failed"  # The game could not be read, the AI could not be asked, or the file not written.
STATUS_BAD_ANSWER = "bad_answer"  # The AI's answer has errors (see problems).
STATUS_CANCELLED = "cancelled"  # Not done because of cancel.


@dataclass(frozen=True)
class GameOutcome:
    """What happened to one game.

    Attributes:
        request: The game and the user's inputs.
        status: One of the STATUS_ constants.
        detail: The reason for STATUS_FAILED ("" otherwise).
        error_kind: For STATUS_FAILED because the AI could not be asked, the kind of
            provider_base.ProviderError ("" otherwise).
        problems: The problems of the answer (errors for STATUS_BAD_ANSWER, warnings for STATUS_DONE).
        answer_text: The AI's answer as it was given ("" if there was none), so that the user can see it.
        generation: The AI's answer and its numbers of tokens, or None if the AI was not asked.
        backup: The copy of the file made before writing, or None.
    """

    request: GameRequest
    status: str
    detail: str = ""
    error_kind: str = ""
    problems: tuple[AnswerProblem, ...] = ()
    answer_text: str = ""
    generation: Generation | None = None
    backup: Path | None = None


def _ignore(*_arguments) -> None:
    """Do nothing (the default of a listener)."""


@dataclass(frozen=True)
class BatchListener:
    """What the screen is told while the games are done (each may be left out).

    Attributes:
        on_start: Called with (index from 0, number of games, request) before each game.
        on_text: Called with each piece of the AI's answer as it arrives.
        on_finish: Called with the outcome after each game.
    """

    on_start: Callable[[int, int, GameRequest], None] = field(default=_ignore)
    on_text: Callable[[str], None] = field(default=_ignore)
    on_finish: Callable[[GameOutcome], None] = field(default=_ignore)


def run_listed_games(
    requests: list[GameRequest],
    provider: Provider,
    text: PromptText,
    history: CommentaryHistory | None,
    listener: BatchListener | None = None,
    cancel: threading.Event | None = None,
    not_analyzed: Iterable[str] = (),
    clock: Callable[[], int] = time.time_ns,
    conditions: ExtractSettings = ExtractSettings(),
) -> list[GameOutcome]:
    """Do the games chosen in the list of new games (see commentary.candidates), and update the list for next time.

    The same as run_batch, and then: the other games of the list that KaTrain has not analyzed
    (not_analyzed, by name) are made pending, and the time of the start of the run becomes
    the time from which changed games are shown.

    Args:
        requests, provider, text, history, listener, cancel, conditions: As in run_batch.
        not_analyzed: The names of the other games in the list that KaTrain has not analyzed.
        clock: Returns the current time in nanoseconds (tests give a fixed time).

    Returns:
        The outcome of each game, in the order of the requests.
    """
    started_ns = clock()
    outcomes = run_batch(requests, provider, text, history, listener, cancel, conditions)
    if history is not None:
        for name in not_analyzed:
            history.mark_pending(name)
        history.set_since_ns(started_ns)
    return outcomes


def run_batch(
    requests: list[GameRequest],
    provider: Provider,
    text: PromptText,
    history: CommentaryHistory | None,
    listener: BatchListener | None = None,
    cancel: threading.Event | None = None,
    conditions: ExtractSettings = ExtractSettings(),
) -> list[GameOutcome]:
    """Give the games to the AI one after another, and write the answers.

    Args:
        requests: The games to do, with the user's inputs.
        provider: The AI.
        text: The parts of the prompt that the user can change.
        history: Where the games are remembered, or None if it cannot be used.
        listener: What the screen is told.
        cancel: When set, no more games are started, and the current one is not written.
        conditions: The quiz's conditions for choosing problems: the moves that become problems are explained.

    Returns:
        The outcome of each game, in the order of the requests.
    """
    listener = listener or BatchListener()
    cancel = cancel or threading.Event()
    outcomes = []
    for index, request in enumerate(requests):
        if cancel.is_set():
            outcome = GameOutcome(request, STATUS_CANCELLED)
        else:
            listener.on_start(index, len(requests), request)
            outcome = _run_game(request, provider, text, history, listener.on_text, cancel, conditions)
        _remember(history, outcome)
        listener.on_finish(outcome)
        outcomes.append(outcome)
    return outcomes


def _run_game(
    request: GameRequest,
    provider: Provider,
    text: PromptText,
    history: CommentaryHistory | None,
    on_text: Callable[[str], None],
    cancel: threading.Event,
    conditions: ExtractSettings,
) -> GameOutcome:
    """Do one game: prepare it, ask the AI, check the answer, and write it."""
    try:
        prepared = prepare_game(request, text, conditions)
    except NotAnalyzedError:
        return GameOutcome(request, STATUS_NOT_ANALYZED)
    except NothingToExplainError:
        return GameOutcome(request, STATUS_NOTHING)
    except Exception as error:  # A broken file must not stop the other games.
        return GameOutcome(request, STATUS_FAILED, str(error) or type(error).__name__)
    try:
        generation = provider.generate(prepared.prompt, on_text, cancel)
    except ProviderError as error:
        return GameOutcome(request, STATUS_FAILED, error.detail, error.kind)
    if cancel.is_set():
        return GameOutcome(request, STATUS_CANCELLED, answer_text=generation.text, generation=generation)
    answer = check_answer(prepared, generation.text)
    if not answer.ok:
        return GameOutcome(
            request, STATUS_BAD_ANSWER, problems=answer.problems, answer_text=generation.text, generation=generation
        )
    try:
        result = finish_game(prepared, answer, history)
    except (OSError, ValueError) as error:
        return GameOutcome(
            request,
            STATUS_FAILED,
            str(error),
            problems=answer.problems,
            answer_text=generation.text,
            generation=generation,
        )
    return GameOutcome(
        request,
        STATUS_DONE,
        problems=answer.problems,
        answer_text=generation.text,
        generation=generation,
        backup=result.backup,
    )


def _remember(history: CommentaryHistory | None, outcome: GameOutcome) -> None:
    """Remember the inputs of a game, and make it pending if it did not get its commentary.

    A game with nothing to explain is remembered as done (it is not listed again until it changes).
    """
    if history is None or outcome.status == STATUS_DONE:
        return  # A done game was remembered when it was written.
    request = outcome.request
    history.save_inputs(request.name, request.my_color, request.my_rank, request.relation)
    if outcome.status == STATUS_NOTHING and request.path.exists():
        history.mark_done(request.name, request.path.stat().st_mtime_ns)
    else:
        history.mark_pending(request.name)
