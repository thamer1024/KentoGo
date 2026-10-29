"""The API mode of the AI commentary, one game at a time.

1. The user chooses a game (the first values of the inputs are filled in) and checks them.
2. "Ask the AI" sends the prompt to the AI chosen in the settings (after asking, if the game
   already has an AI commentary). The answer is shown as it arrives.
3. When the answer is complete and has no errors, it is written into the SGF file. The
   message tells what was written, the problems of the answer, and the numbers of tokens.
4. "Stop" stops the AI: nothing is written.

The work is done by commentary.batch (with one game), in a background thread.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from kentogo.commentary.batch import STATUS_DONE, BatchListener, GameOutcome, run_batch
from kentogo.commentary.candidates import GameCandidate
from kentogo.commentary.job import GameRequest
from kentogo.commentary.provider_base import ProviderError
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.gui import commentary_texts, texts, theme
from kentogo.gui.dialogs import confirm, show_long_message, show_message
from kentogo.gui.game_chooser import GameChooser
from kentogo.gui.game_inputs import GameInputs, request_for
from kentogo.gui.widgets import (
    fitting_label,
    flat_button,
    in_main_thread,
    set_background,
    set_text,
    text_box,
    title_label,
)

BUTTON_HEIGHT = 44  # dp


class ApiScreen(BoxLayout):
    """The screen of the API mode for one game."""

    def __init__(self, workspace: CommentaryWorkspace, folder: Path, on_back: Callable[[], None], **kwargs):
        """Make the screen, and open the dialog to choose a game.

        Args:
            workspace: What the AI commentary needs (settings, history, prompt file, the AI).
            folder: The games folder.
            on_back: Called by the back button (the AI is stopped first).
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kwargs)
        set_background(self, theme.BOX_BACKGROUND_COLOR)
        self.workspace = workspace
        self.folder = folder
        self.candidate: GameCandidate | None = None
        self.cancel_event: threading.Event | None = None  # Set while the AI is asked.
        self._on_back = on_back
        self._build()
        in_main_thread(self.choose_game)()

    def _build(self) -> None:
        """Make the widgets: the game, the inputs, the buttons, the answer and the message."""
        game_row = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(8))
        game_row.add_widget(flat_button(texts.lazy("viewer_choose"), self.choose_game, size_hint_x=0.25))
        self.game_label = fitting_label(dp(BUTTON_HEIGHT))
        set_text(self.game_label, texts.lazy("commentary_no_game"))
        game_row.add_widget(self.game_label)
        game_row.add_widget(flat_button(texts.lazy("copy_file_name"), self.copy_name, size_hint_x=None, width=dp(72)))
        self.inputs = GameInputs()
        run_row = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(8))
        run_row.add_widget(flat_button(texts.lazy("commentary_run"), self.run))
        run_row.add_widget(flat_button(texts.lazy("commentary_stop"), self.stop))
        self.answer_box = text_box(readonly=True)
        self.message_label = fitting_label(dp(28))
        widgets = [
            game_row,
            self.inputs,
            run_row,
            title_label(texts.lazy("commentary_answer_stream")),
            self.answer_box,
            self.message_label,
            flat_button(texts.lazy("back_to_commentary"), self.back, size_hint_y=None, height=dp(BUTTON_HEIGHT)),
        ]
        for widget in widgets:
            self.add_widget(widget)

    def choose_game(self) -> None:
        """Open the dialog that lists the games (not while the AI is asked)."""
        if self.cancel_event is None:
            GameChooser(self.folder, self._game_chosen).open()

    def copy_name(self) -> None:
        """Copy the name of the chosen game's SGF file to the clipboard (nothing if no game is chosen)."""
        if self.candidate is not None:
            Clipboard.copy(self.candidate.name)

    def _game_chosen(self, path: Path) -> None:
        """Read the chosen game in the background, and show it with the first values of the inputs."""
        self.answer_box.text = ""
        set_text(self.message_label, str)
        set_text(self.game_label, texts.lazy("commentary_reading"))
        threading.Thread(
            target=lambda: in_main_thread(self._show_game)(self.workspace.candidate(path)), daemon=True
        ).start()

    def _show_game(self, candidate: GameCandidate) -> None:
        """Show a game that has been read, or tell why it cannot be used."""
        if candidate.error:
            set_text(self.game_label, texts.lazy("commentary_no_game"))
            show_message(texts.text("error_title"), texts.text("commentary_read_failed", reason=candidate.error))
            return
        self.candidate = candidate
        set_text(self.game_label, lambda: candidate.name)
        self.inputs.set_values(candidate.my_color, candidate.my_rank, candidate.relation)
        if not candidate.analyzed:
            show_message(texts.text("mode_commentary"), texts.text("commentary_not_analyzed"))

    def run(self) -> None:
        """Ask the AI about the chosen game, asking first if it already has an AI commentary."""
        if self.cancel_event is not None:
            return
        if self.candidate is None:
            show_message(texts.text("mode_commentary"), texts.text("commentary_no_game"))
            return
        request = request_for(self.candidate, self.inputs)
        if request is None:
            show_message(texts.text("mode_commentary"), texts.text("commentary_choose_color"))
        elif self.candidate.has_ai:
            replace_label = texts.text("commentary_replace")
            confirm(
                texts.text("commentary_replace_question"), lambda: self._start(request), lambda: None, replace_label
            )
        else:
            self._start(request)

    def _start(self, request: GameRequest) -> None:
        """Ask the AI in a background thread, showing the answer as it arrives."""
        settings = self.workspace.commentary_settings()
        cancel = threading.Event()
        self.cancel_event = cancel
        self.answer_box.text = ""
        set_text(self.message_label, lambda: texts.text("commentary_asking", model=settings.model))
        listener = BatchListener(on_text=in_main_thread(self._add_text))

        def work() -> None:
            """Run in the background thread. Errors are shown on the screen."""
            try:
                provider = self.workspace.provider()
            except ProviderError as error:
                message = commentary_texts.provider_error_text(error.kind, error.detail, settings.api_key_env)
                in_main_thread(self._failed)(message)
                return
            text, problems = self.workspace.prompt_text(commentary_texts.commentary_language())
            history = self.workspace.open_history()
            try:
                conditions = self.workspace.conditions()
                outcome = run_batch([request], provider, text, history, listener, cancel, conditions)[0]
            except Exception as error:  # The screen must stay usable.
                in_main_thread(self._failed)(texts.text("action_failed", reason=error))
                return
            finally:
                if history is not None:
                    history.close()
            file_problems = commentary_texts.prompt_file_problems_text(problems)
            in_main_thread(self._finished)(outcome, settings.api_key_env, file_problems)

        threading.Thread(target=work, daemon=True).start()

    def _add_text(self, piece: str) -> None:
        """Add a piece of the AI's answer to the box."""
        self.answer_box.text += piece

    def _failed(self, message: str) -> None:
        """Tell that the AI could not be asked."""
        self.cancel_event = None
        set_text(self.message_label, lambda: message)
        show_message(texts.text("error_title"), message)

    def _finished(self, outcome: GameOutcome, api_key_env: str, file_problems: str) -> None:
        """Tell what happened to the game, and show the whole answer if it could not be written."""
        self.cancel_event = None
        message = commentary_texts.outcome_text(outcome, api_key_env)
        if file_problems:
            message = f"{message}\n{file_problems}"
        set_text(self.message_label, lambda: message)
        if outcome.status == STATUS_DONE and self.candidate is not None:
            self.candidate = replace(self.candidate, has_ai=True)
        if outcome.answer_text and not self.answer_box.text:
            self.answer_box.text = outcome.answer_text
        show_long_message(texts.text("mode_commentary"), message)

    def stop(self) -> None:
        """Stop the AI. Nothing is written."""
        if self.cancel_event is not None:
            self.cancel_event.set()

    def back(self) -> None:
        """Stop the AI, and go back to the menu."""
        self.stop()
        self._on_back()
