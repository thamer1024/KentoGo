"""The paste mode of the AI commentary, one game at a time.

1. The user chooses a game (the first values of the inputs are filled in) and checks them.
2. "Make the prompt" makes the prompt (after asking, if the game already has an AI commentary).
   The prompt is shown with a copy button; the user pastes it into the chat screen of any AI.
3. The user pastes the AI's answer and presses "Apply": it is checked, and written into the
   SGF file if it has no errors. With errors, they are shown, and the user can paste again.
4. "Cancel" forgets the prompt and the answer: nothing is written or remembered.

The work is done by commentary.paste; files are read and written in background threads.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from kentogo.commentary.candidates import GameCandidate
from kentogo.commentary.job import GameRequest, NotAnalyzedError, NothingToExplainError, PreparedGame
from kentogo.commentary.paste import PasteResult, apply_paste, prepare_paste, remember_not_analyzed
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.gui import commentary_texts, texts, theme
from kentogo.gui.dialogs import confirm, show_message
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


class PasteScreen(BoxLayout):
    """The screen of the paste mode."""

    def __init__(self, workspace: CommentaryWorkspace, folder: Path, on_back: Callable[[], None], **kwargs):
        """Make the screen, and open the dialog to choose a game.

        Args:
            workspace: What the AI commentary needs (settings, history, prompt file).
            folder: The games folder.
            on_back: Called by the back button.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kwargs)
        set_background(self, theme.BOX_BACKGROUND_COLOR)
        self.workspace = workspace
        self.folder = folder
        self.candidate: GameCandidate | None = None
        self.prepared: PreparedGame | None = None
        self._build(on_back)
        in_main_thread(self.choose_game)()

    def _build(self, on_back: Callable[[], None]) -> None:
        """Make the widgets: the game, the inputs, the prompt, the answer, the messages and the buttons."""
        game_row = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(8))
        game_row.add_widget(flat_button(texts.lazy("viewer_choose"), self.choose_game, size_hint_x=0.25))
        self.game_label = fitting_label(dp(BUTTON_HEIGHT))
        set_text(self.game_label, texts.lazy("commentary_no_game"))
        game_row.add_widget(self.game_label)
        game_row.add_widget(flat_button(texts.lazy("copy_file_name"), self.copy_name, size_hint_x=None, width=dp(72)))
        self.inputs = GameInputs()
        self.prompt_box = text_box(readonly=True)
        self.answer_box = text_box(readonly=False)
        self.message_label = fitting_label(dp(28))
        widgets = [
            game_row,
            self.inputs,
            flat_button(texts.lazy("commentary_make_prompt"), self.make_prompt, size_hint_y=None, height=dp(44)),
            title_label(texts.lazy("commentary_prompt_title")),
            self.prompt_box,
            flat_button(texts.lazy("commentary_copy"), self.copy_prompt, size_hint_y=None, height=dp(40)),
            title_label(texts.lazy("commentary_answer_title")),
            self.answer_box,
            self._answer_buttons(),
            self.message_label,
            flat_button(texts.lazy("back_to_commentary"), on_back, size_hint_y=None, height=dp(BUTTON_HEIGHT)),
        ]
        for widget in widgets:
            self.add_widget(widget)

    def _answer_buttons(self) -> BoxLayout:
        """Make the row with the apply and cancel buttons."""
        row = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(8))
        row.add_widget(flat_button(texts.lazy("commentary_apply"), self.apply_answer))
        row.add_widget(flat_button(texts.lazy("commentary_cancel"), self.cancel))
        return row

    def choose_game(self) -> None:
        """Open the dialog that lists the games."""
        GameChooser(self.folder, self._game_chosen).open()

    def copy_name(self) -> None:
        """Copy the name of the chosen game's SGF file to the clipboard (nothing if no game is chosen)."""
        if self.candidate is not None:
            Clipboard.copy(self.candidate.name)

    def _game_chosen(self, path: Path) -> None:
        """Read the chosen game in the background, and show it with the first values of the inputs."""
        self.cancel()
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

    def make_prompt(self) -> None:
        """Make the prompt of the chosen game, asking first if it already has an AI commentary."""
        request = self._request()
        if request is None:
            return
        if self.candidate.has_ai:
            replace_label = texts.text("commentary_replace")
            confirm(
                texts.text("commentary_replace_question"), lambda: self._prepare(request), lambda: None, replace_label
            )
        else:
            self._prepare(request)

    def _request(self) -> GameRequest | None:
        """Return the request from the inputs, or tell what is missing and return None."""
        if self.candidate is None:
            show_message(texts.text("mode_commentary"), texts.text("commentary_no_game"))
            return None
        request = request_for(self.candidate, self.inputs)
        if request is None:
            show_message(texts.text("mode_commentary"), texts.text("commentary_choose_color"))
        return request

    def _prepare(self, request: GameRequest) -> None:
        """Make the prompt in the background (reading the game and the prompt file)."""

        def work() -> None:
            text, problems = self.workspace.prompt_text(commentary_texts.commentary_language())
            try:
                prepared = prepare_paste(request, text, self.workspace.conditions())
            except NotAnalyzedError:
                self._remember_not_analyzed(request)
                in_main_thread(show_message)(texts.text("mode_commentary"), texts.text("commentary_not_analyzed"))
                return
            except NothingToExplainError:
                in_main_thread(show_message)(texts.text("mode_commentary"), texts.text("commentary_status_nothing"))
                return
            except (OSError, ValueError) as error:
                reason = texts.text("commentary_read_failed", reason=error)
                in_main_thread(show_message)(texts.text("error_title"), reason)
                return
            in_main_thread(self._show_prompt)(prepared, commentary_texts.prompt_file_problems_text(problems))

        threading.Thread(target=work, daemon=True).start()

    def _remember_not_analyzed(self, request: GameRequest) -> None:
        """Remember a game that KaTrain has not analyzed as pending (in the background thread)."""
        history = self.workspace.open_history()
        if history is not None:
            try:
                remember_not_analyzed(request, history)
            finally:
                history.close()

    def _show_prompt(self, prepared: PreparedGame, problems: str) -> None:
        """Show the prompt, and the problems of the prompt file if there are any."""
        self.prepared = prepared
        self.prompt_box.text = prepared.prompt.for_paste()
        self.prompt_box.cursor = (0, 0)
        set_text(self.message_label, lambda: problems)

    def copy_prompt(self) -> None:
        """Copy the prompt to the clipboard."""
        if self.prepared is not None:
            Clipboard.copy(self.prompt_box.text)
            set_text(self.message_label, texts.lazy("commentary_copied"))

    def apply_answer(self) -> None:
        """Check the pasted answer and write it into the SGF file in the background."""
        prepared, answer = self.prepared, self.answer_box.text
        if prepared is None or not answer.strip():
            return

        def work() -> None:
            history = self.workspace.open_history()
            try:
                result = apply_paste(prepared, answer, history)
            finally:
                if history is not None:
                    history.close()
            in_main_thread(self._show_result)(result)

        threading.Thread(target=work, daemon=True).start()

    def _show_result(self, result: PasteResult) -> None:
        """Tell what happened to the answer: written, not written because of its errors, or failed."""
        problems = commentary_texts.answer_problems_text(result.answer.problems)
        if result.written is not None:
            self.cancel()
            message = commentary_texts.written_text(result.written)
            show_message(texts.text("mode_commentary"), f"{message}\n{problems}".rstrip())
        elif result.error:
            set_text(self.message_label, lambda: texts.text("commentary_write_failed", reason=result.error))
        else:
            set_text(self.message_label, lambda: f"{texts.text('commentary_not_written')}\n{problems}")

    def cancel(self) -> None:
        """Forget the prompt and the answer (nothing is written or remembered)."""
        self.prepared = None
        self.prompt_box.text = ""
        self.answer_box.text = ""
        set_text(self.message_label, str)
