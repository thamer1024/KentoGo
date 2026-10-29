"""The API mode of the AI commentary for the new games: the list of games, and the AI for each checked game.

1. The first time, the user chooses how far back to look (one week, one month, three months,
   all games, or a date; see commentary.since). Later, the games changed since the last run
   are listed, with the games that were waiting for KaTrain's analysis.
2. Each game is one row: a check box, the board at the end, the name and the players, the
   inputs (the user's color, rank and the opponent), the status, and a button that excludes
   the game from the list for good.
3. "Ask the AI" gives the checked games to the AI one after another (see
   commentary.batch.run_listed_games). The answer of the current game is shown as it arrives,
   and the status of each row tells what happened. "Stop" stops after the current game,
   which is not written.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from kentogo.commentary.batch import STATUS_DONE, BatchListener, GameOutcome, run_listed_games
from kentogo.commentary.candidates import GameCandidate
from kentogo.commentary.job import GameRequest
from kentogo.commentary.provider_base import ProviderError
from kentogo.commentary.since import SINCE_CHOICES, SINCE_DATE, since_ns_for
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.gui import commentary_texts, texts, theme
from kentogo.gui.board_view import BoardView
from kentogo.gui.board_widget import BoardWidget
from kentogo.gui.check_box import MaterialCheckBox
from kentogo.gui.dialogs import bind_dialog_keys, choose, show_long_message, show_message
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
ROW_HEIGHT = 104  # dp. One game of the list.
BOARD_SIZE = 96  # dp. The small board at the end of the game.


class GameRow(BoxLayout):
    """One game of the list.

    Attributes:
        candidate: The game, with the first values of the inputs.
        check: The check box: the game is given to the AI when it is checked.
        inputs: The user's color, rank and the opponent.
    """

    def __init__(self, candidate: GameCandidate, on_exclude: Callable[[GameRow], None], **kwargs):
        """Make the row of a game."""
        super().__init__(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(8), padding=dp(4), **kwargs)
        set_background(self, theme.BACKGROUND_COLOR)
        self.candidate = candidate
        self.check = MaterialCheckBox(size_hint=(None, None), size=(dp(32), dp(32)), active=candidate.analyzed)
        board = BoardWidget(size_hint=(None, None), size=(dp(BOARD_SIZE), dp(BOARD_SIZE)))
        if candidate.final_state is not None:
            board.show(BoardView(candidate.size, dict(candidate.final_state.stones)))
        self.inputs = GameInputs()
        self.inputs.set_values(candidate.my_color, candidate.my_rank, candidate.relation)
        self.status_label = fitting_label(dp(32), size_hint_x=0.22)
        set_text(self.status_label, lambda: _first_status(candidate))
        self.add_widget(self.check)
        self.add_widget(board)
        self.add_widget(self._middle())
        self.add_widget(self.status_label)
        self.add_widget(flat_button(texts.lazy("commentary_exclude"), lambda: on_exclude(self), size_hint_x=0.08))

    def _middle(self) -> BoxLayout:
        """Make the middle of the row: the name and the players above the inputs."""
        box = BoxLayout(orientation="vertical", spacing=dp(4))
        candidate = self.candidate
        name = fitting_label(dp(24))
        set_text(name, lambda: f"{candidate.name}　{_players(candidate)}")
        box.add_widget(name)
        box.add_widget(self.inputs)
        return box

    def show_status(self, text: str) -> None:
        """Show the status of the game."""
        set_text(self.status_label, lambda: text)


class BatchScreen(BoxLayout):
    """The screen of the API mode for the new games."""

    def __init__(self, workspace: CommentaryWorkspace, folder: Path, on_back: Callable[[], None], **kwargs):
        """Make the screen, and read the list of new games (asking how far back, the first time).

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
        self.rows: list[GameRow] = []
        self.cancel_event: threading.Event | None = None  # Set while the AI is asked.
        self._on_back = on_back
        self._build()
        self._load()

    def _build(self) -> None:
        """Make the widgets: the title, the list, the answer, the message and the buttons."""
        self.title_label = fitting_label(dp(28))
        set_text(self.title_label, texts.lazy("commentary_batch_loading"))
        self.list_box = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll = ScrollView(size_hint_y=0.6)
        scroll.add_widget(self.list_box)
        self.answer_box = text_box(readonly=True)
        self.answer_box.size_hint_y = 0.4
        self.message_label = fitting_label(dp(28))
        buttons = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(8))
        buttons.add_widget(flat_button(texts.lazy("commentary_run"), self.run))
        buttons.add_widget(flat_button(texts.lazy("commentary_stop"), self.stop))
        buttons.add_widget(flat_button(texts.lazy("back_to_commentary"), self.back))
        for widget in (self.title_label, scroll, title_label(texts.lazy("commentary_answer_stream")), self.answer_box):
            self.add_widget(widget)
        self.add_widget(self.message_label)
        self.add_widget(buttons)

    def _load(self) -> None:
        """Read the list in the background, or ask how far back to look if this is the first time."""

        def work() -> None:
            """Run in the background thread."""
            history = self.workspace.open_history()
            if history is None:
                in_main_thread(self._show_list)([])
                return
            try:
                since_ns = history.since_ns()
                if since_ns is None:
                    in_main_thread(self._ask_since)()
                    return
                games = self.workspace.new_games(self.folder, history, since_ns)
            finally:
                history.close()
            in_main_thread(self._show_list)(games)

        threading.Thread(target=work, daemon=True).start()

    def _ask_since(self) -> None:
        """Ask how far back to look for changed games (only the first time)."""
        choices = [
            (texts.text(f"since_{choice}"), lambda choice=choice: self._since_chosen(choice, ""))
            for choice in SINCE_CHOICES
        ]
        choices[SINCE_CHOICES.index(SINCE_DATE)] = (texts.text(f"since_{SINCE_DATE}"), self._ask_date)
        choose(texts.text("commentary_since_title"), texts.text("commentary_since_question"), choices)

    def _ask_date(self) -> None:
        """Ask the date from which changed games are shown."""
        ask_text(texts.text("commentary_since_date_question"), lambda text: self._since_chosen(SINCE_DATE, text))

    def _since_chosen(self, choice: str, date_text: str) -> None:
        """Remember the chosen time in the history, and read the list."""
        try:
            since_ns = since_ns_for(choice, datetime.now(), date_text)
        except ValueError as error:
            show_message(texts.text("error_title"), texts.text("commentary_since_date_wrong", reason=error))
            self._ask_since()
            return
        history = self.workspace.open_history()
        if history is not None:
            try:
                history.set_since_ns(since_ns)
            finally:
                history.close()
        self._load()

    def _show_list(self, games: list[GameCandidate]) -> None:
        """Show one row for each game."""
        self.list_box.clear_widgets()
        self.rows = [GameRow(game, self.exclude) for game in games if not game.error]
        for row in self.rows:
            self.list_box.add_widget(row)
        key = "commentary_batch_count" if self.rows else "commentary_batch_empty"
        set_text(self.title_label, lambda: texts.text(key, count=len(self.rows)))

    def exclude(self, row: GameRow) -> None:
        """Take a game out of the list for good (not while the AI is asked)."""
        if self.cancel_event is not None:
            return
        history = self.workspace.open_history()
        if history is not None:
            try:
                history.exclude(row.candidate.name)
            finally:
                history.close()
        self.rows.remove(row)
        self.list_box.remove_widget(row)
        set_text(self.title_label, lambda: texts.text("commentary_batch_count", count=len(self.rows)))

    def run(self) -> None:
        """Give the checked games to the AI one after another, in a background thread."""
        if self.cancel_event is not None:
            return
        chosen = [row for row in self.rows if row.check.active]
        if not chosen:
            show_message(texts.text("mode_commentary"), texts.text("commentary_batch_none_checked"))
            return
        requests = [request_for(row.candidate, row.inputs) for row in chosen]
        missing = [row.candidate.name for row, request in zip(chosen, requests, strict=True) if request is None]
        if missing:
            names = "\n".join(missing)
            show_message(texts.text("mode_commentary"), f"{texts.text('commentary_choose_color')}\n{names}")
            return
        not_analyzed = [row.candidate.name for row in self.rows if row not in chosen and not row.candidate.analyzed]
        self._start(requests, not_analyzed)

    def _start(self, requests: list[GameRequest], not_analyzed: list[str]) -> None:
        """Ask the AI about the games in a background thread, showing each answer as it arrives."""
        settings = self.workspace.commentary_settings()
        cancel = threading.Event()
        self.cancel_event = cancel
        listener = BatchListener(
            on_start=in_main_thread(self._game_started),
            on_text=in_main_thread(self._add_text),
            on_finish=in_main_thread(lambda outcome: self._game_finished(outcome, settings.api_key_env)),
        )

        def work() -> None:
            """Run in the background thread. Errors are shown on the screen."""
            try:
                provider = self.workspace.provider()
            except ProviderError as error:
                in_main_thread(self._failed)(
                    commentary_texts.provider_error_text(error.kind, error.detail, settings.api_key_env)
                )
                return
            text, _problems = self.workspace.prompt_text(commentary_texts.commentary_language())
            history = self.workspace.open_history()
            try:
                conditions = self.workspace.conditions()
                outcomes = run_listed_games(
                    requests, provider, text, history, listener, cancel, not_analyzed, conditions=conditions
                )
            except Exception as error:  # The screen must stay usable.
                in_main_thread(self._failed)(texts.text("action_failed", reason=error))
                return
            finally:
                if history is not None:
                    history.close()
            in_main_thread(self._all_finished)(outcomes, settings.api_key_env)

        threading.Thread(target=work, daemon=True).start()

    def _row(self, name: str) -> GameRow | None:
        """Return the row of a game, by the name of its file."""
        return next((row for row in self.rows if row.candidate.name == name), None)

    def _game_started(self, index: int, total: int, request: GameRequest) -> None:
        """Show which game the AI is working on."""
        self.answer_box.text = ""
        row = self._row(request.name)
        if row is not None:
            row.show_status(texts.text("commentary_status_running"))
        set_text(
            self.message_label,
            lambda: texts.text("commentary_batch_progress", number=index + 1, total=total, name=request.name),
        )

    def _add_text(self, piece: str) -> None:
        """Add a piece of the AI's answer to the box."""
        self.answer_box.text += piece

    def _game_finished(self, outcome: GameOutcome, api_key_env: str) -> None:
        """Show the status of a game that is finished. A game that got its commentary is unchecked."""
        row = self._row(outcome.request.name)
        if row is None:
            return
        row.show_status(commentary_texts.status_text(outcome, api_key_env))
        if outcome.status == STATUS_DONE:
            row.check.active = False

    def _all_finished(self, outcomes: list[GameOutcome], api_key_env: str) -> None:
        """Tell how many games got their commentary, and show what happened to each game."""
        self.cancel_event = None
        done = sum(outcome.status == STATUS_DONE for outcome in outcomes)
        summary = texts.text("commentary_batch_finished", done=done, total=len(outcomes))
        set_text(self.message_label, lambda: summary)
        details = [f"■ {o.request.name}\n{commentary_texts.outcome_text(o, api_key_env)}" for o in outcomes]
        show_long_message(texts.text("mode_commentary"), "\n\n".join([summary, *details]))

    def _failed(self, message: str) -> None:
        """Tell that the AI could not be asked."""
        self.cancel_event = None
        set_text(self.message_label, lambda: message)
        show_message(texts.text("error_title"), message)

    def stop(self) -> None:
        """Stop after the current game (which is not written)."""
        if self.cancel_event is not None:
            self.cancel_event.set()

    def back(self) -> None:
        """Stop the AI, and go back to the menu."""
        self.stop()
        self._on_back()


def ask_text(question: str, on_ok: Callable[[str], None]) -> None:
    """Ask the user to write a short text in a dialog, and give it to on_ok (nothing happens on cancel)."""
    popup = Popup(
        title=texts.text("mode_commentary"),
        title_size=sp(18),
        size_hint=(0.5, None),
        height=dp(220),
        background="",
        background_color=theme.BACKGROUND_COLOR,
        separator_color=theme.BUTTON_COLOR,
        auto_dismiss=False,
    )
    field = TextInput(multiline=False, size_hint_y=None, height=dp(36))

    def answer() -> None:
        """Close the dialog, then give the text."""
        popup.dismiss()
        on_ok(field.text)

    content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    question_label = fitting_label(dp(28))
    question_label.text = question
    content.add_widget(question_label)
    content.add_widget(field)
    buttons = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(8))
    buttons.add_widget(flat_button(texts.text("ok"), answer))
    buttons.add_widget(flat_button(texts.text("cancel"), popup.dismiss))
    content.add_widget(buttons)
    popup.content = content
    bind_dialog_keys(popup, answer, popup.dismiss)
    popup.open()


def _players(candidate: GameCandidate) -> str:
    """Return the line about the players and the result of a game."""
    return commentary_texts.players_text(candidate.black_name, candidate.white_name, candidate.result)


def _first_status(candidate: GameCandidate) -> str:
    """Return the status of a game before the AI is asked: waiting, or not analyzed by KaTrain."""
    return texts.text("commentary_status_waiting" if candidate.analyzed else "commentary_status_not_analyzed")
