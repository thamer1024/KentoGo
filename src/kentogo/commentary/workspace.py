"""What the screens of the AI commentary need from the rest of KentoGo, without Kivy.

The screens get one CommentaryWorkspace, and each thing they do is one call to it: they do not
put the steps together. It reads the settings and the prompt file each time they are needed (so
that changes made on the settings screen are used at once), and opens the history in the thread
that uses it (SQLite connections cannot be shared between threads).
"""

from __future__ import annotations

import sqlite3
import sys
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kentogo.commentary.batch import BatchListener, GameOutcome, run_batch, run_listed_games
from kentogo.commentary.candidates import GameCandidate, candidate_for, list_candidates
from kentogo.commentary.commentary_settings import CommentarySettings
from kentogo.commentary.history import CommentaryHistory, history_path
from kentogo.commentary.job import GameRequest, NotAnalyzedError, PreparedGame
from kentogo.commentary.language import JAPANESE, CommentaryLanguage
from kentogo.commentary.paste import PasteResult, apply_paste, prepare_paste, remember_not_analyzed
from kentogo.commentary.prompt_text import PromptFileProblem, PromptText, load_prompt_text
from kentogo.commentary.provider_base import Provider
from kentogo.commentary.providers import make_provider
from kentogo.commentary.since import since_ns_for
from kentogo.mistakes.extract import ExtractSettings


@dataclass(frozen=True)
class CommentaryWorkspace:
    """What the screens of the AI commentary need.

    The settings are given as functions that read them from the settings file, so that this
    class does not depend on how the settings of the whole app are kept.

    Attributes:
        settings_path: The settings file (the history and the prompt file are next to it).
        read_commentary_settings: Reads the settings of the AI commentary from the settings file.
        read_extract_settings: Reads the quiz's conditions for choosing problems from the settings file.
        my_names: The user's names (the quiz setting), to find the user's color.
    """

    settings_path: Path
    read_commentary_settings: Callable[[], CommentarySettings]
    read_extract_settings: Callable[[], ExtractSettings]
    my_names: tuple[str, ...] = ()

    def commentary_settings(self) -> CommentarySettings:
        """Return the settings of the AI commentary, as they are in the settings file now."""
        return self.read_commentary_settings()

    def conditions(self) -> ExtractSettings:
        """Return the quiz's conditions for choosing problems: the AI explains the moves that become problems."""
        return self.read_extract_settings()

    def provider(self) -> Provider:
        """Make the AI chosen in the settings file now.

        Raises:
            ProviderError: If the API key is not set, or the package of the API is not installed.
        """
        return make_provider(self.commentary_settings())

    def new_games(self, folder: Path, history: CommentaryHistory, since_ns: int) -> list[GameCandidate]:
        """Return the list of new games (see commentary.candidates), with the last rank as the default rank."""
        return list_candidates(folder, history, since_ns, self.my_names, history.last_rank())

    def open_history(self) -> CommentaryHistory | None:
        """Open the history (in the thread that will use it), or return None if it cannot be used."""
        path = history_path(self.settings_path)
        try:
            return CommentaryHistory(path)
        except (sqlite3.Error, OSError) as error:
            print(f"cannot use the commentary history {path}: {error}", file=sys.stderr)
            return None

    def prompt_text(self, language: CommentaryLanguage = JAPANESE) -> tuple[PromptText, list[PromptFileProblem]]:
        """Read the parts of the prompt that the user can change, in the language of the commentary.

        See commentary.prompt_text.
        """
        return load_prompt_text(self.settings_path, language)

    def candidate(self, path: Path) -> GameCandidate:
        """Read a game chosen by the user, with the first values of the inputs (the last rank as the default)."""
        with self._opened_history() as history:
            default_rank = history.last_rank() if history is not None else ""
            return candidate_for(path, history, self.my_names, default_rank)

    def games_to_list(self, folder: Path) -> list[GameCandidate] | None:
        """Return the new games, or None the first time (the user must choose how far back to look; see choose_since).

        Without a usable history, there are no games to list.
        """
        with self._opened_history() as history:
            if history is None:
                return []
            since_ns = history.since_ns()
            return None if since_ns is None else self.new_games(folder, history, since_ns)

    def choose_since(self, choice: str, date_text: str, now: datetime) -> None:
        """Remember how far back to look for new games (see commentary.since).

        Raises:
            ValueError: If the date written by the user cannot be read.
        """
        since_ns = since_ns_for(choice, now, date_text)
        with self._opened_history() as history:
            if history is not None:
                history.set_since_ns(since_ns)

    def exclude_game(self, name: str) -> None:
        """Take a game out of the list of new games for good."""
        with self._opened_history() as history:
            if history is not None:
                history.exclude(name)

    def ask_game(
        self, request: GameRequest, language: CommentaryLanguage, listener: BatchListener, cancel: threading.Event
    ) -> tuple[GameOutcome, list[PromptFileProblem]]:
        """Ask the AI about one game and write the answer (see commentary.batch.run_batch).

        Args:
            request: The game and the user's inputs.
            language: The language of the commentary.
            listener: What the screen is told.
            cancel: When set, the answer is not written.

        Returns:
            What happened to the game, and the problems of the prompt file.

        Raises:
            ProviderError: If the AI cannot be used.
        """
        provider = self.provider()
        text, problems = self.prompt_text(language)
        with self._opened_history() as history:
            return run_batch([request], provider, text, history, listener, cancel, self.conditions())[0], problems

    def ask_listed_games(
        self,
        requests: list[GameRequest],
        not_analyzed: Iterable[str],
        language: CommentaryLanguage,
        listener: BatchListener,
        cancel: threading.Event,
    ) -> list[GameOutcome]:
        """Ask the AI about the games chosen in the list (see commentary.batch.run_listed_games).

        Args:
            requests: The games, with the user's inputs.
            not_analyzed: The names of the other games in the list that KaTrain has not analyzed.
            language: The language of the commentary.
            listener: What the screen is told.
            cancel: When set, no more games are started, and the current one is not written.

        Raises:
            ProviderError: If the AI cannot be used.
        """
        provider = self.provider()
        text, _problems = self.prompt_text(language)
        with self._opened_history() as history:
            return run_listed_games(
                requests, provider, text, history, listener, cancel, not_analyzed, conditions=self.conditions()
            )

    def prepare_for_paste(
        self, request: GameRequest, language: CommentaryLanguage
    ) -> tuple[PreparedGame, list[PromptFileProblem]]:
        """Make the prompt of a game for the paste mode, with the problems of the prompt file.

        Raises:
            NotAnalyzedError: If KaTrain has not analyzed the game (it is remembered as pending).
            NothingToExplainError: If no move of the user is to be explained.
            OSError, ValueError: If the file cannot be read.
        """
        text, problems = self.prompt_text(language)
        try:
            return prepare_paste(request, text, self.conditions()), problems
        except NotAnalyzedError:
            with self._opened_history() as history:
                remember_not_analyzed(request, history)
            raise

    def apply_pasted_answer(self, prepared: PreparedGame, answer: str) -> PasteResult:
        """Check a pasted answer, and write it into the SGF file if it has no errors."""
        with self._opened_history() as history:
            return apply_paste(prepared, answer, history)

    @contextmanager
    def _opened_history(self) -> Iterator[CommentaryHistory | None]:
        """Open the history for a piece of work (None if it cannot be used), and close it at the end."""
        history = self.open_history()
        try:
            yield history
        finally:
            if history is not None:
                history.close()
