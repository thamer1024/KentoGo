"""What the screens of the AI commentary need from the rest of KentoGo, without Kivy.

The screens get one CommentaryWorkspace. It reads the settings and the prompt file each
time they are needed (so that changes made on the settings screen are used at once), and
opens the history in the thread that uses it (SQLite connections cannot be shared between
threads).
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kentogo.commentary.candidates import GameCandidate, candidate_for, list_candidates
from kentogo.commentary.commentary_settings import CommentarySettings
from kentogo.commentary.history import CommentaryHistory, history_path
from kentogo.commentary.language import JAPANESE, CommentaryLanguage
from kentogo.commentary.prompt_text import PromptFileProblem, PromptText, load_prompt_text
from kentogo.commentary.provider_base import Provider
from kentogo.commentary.providers import make_provider
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
        history = self.open_history()
        try:
            default_rank = history.last_rank() if history is not None else ""
            return candidate_for(path, history, self.my_names, default_rank)
        finally:
            if history is not None:
                history.close()
