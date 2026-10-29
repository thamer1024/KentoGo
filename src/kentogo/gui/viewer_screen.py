"""The screen that shows a game move by move, with KaTrain's evaluation and the AI commentary.

A game is chosen in a wide dialog (see gui.game_chooser), which opens at once when the
screen is opened from the top screen, and again with the "choose a game" button. On the
left is the board. On the right are
the move number, KaTrain's loss and best move, the AI commentary and the user's notes, and
the buttons: to the first or last move, one move back or forward, to the previous or next
move with an AI commentary, and the review of the whole game. The slider moves through the
game. The keys ← → move one move, ↑ ↓ go to the previous or next AI commentary, and
Home / End go to the first or last move.

At a move, KaTrain's predicted sequence and the other branches of the SGF file can be
shown in place of the move. Tab shows the first sequence (its first move replaces the move
of the game), then the next ones, and then the game again at the move where they branch
off. Space / Shift+Space and ← → move one move through the game, or through the sequence
while one is shown. Esc returns to the game at that move. The other keys and the slider
return to the game first. Two buttons do the same as Tab and Esc.

When a sequence is shown to its last move, T (or a button) shows the territory and the
standing there, as KaTrain does, and how much better it is than the game after the same
number of moves (see katago.estimate); T again hides them, and so does moving.

When the comparison model can be used, Tab after the last sequence analyzes the position
before the move with it: its best sequence then comes last at that move, with its own mark
on the board.

The screen can also be opened on one game at one move (from the quiz, see open_game).
What is drawn and written comes from gui.viewer_model, and the game from record.game_record.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider

from kentogo.common import sgf
from kentogo.gui import texts, theme, viewer_model
from kentogo.gui.board_widget import BoardWidget
from kentogo.gui.dialogs import show_long_message, show_message
from kentogo.gui.file_name_row import FileNameRow
from kentogo.gui.game_chooser import GameChooser
from kentogo.gui.widgets import fitting_label, flat_button, growing_label, in_main_thread, set_background, set_text
from kentogo.katago.estimate import Standing
from kentogo.katago.evaluate import Models
from kentogo.mistakes.problem import Variation
from kentogo.record.game_record import (
    GameRecord,
    next_ai_position,
    previous_ai_position,
    read_game_record,
    review_text,
)
from kentogo.viewer.analyses import GameAnalyses

KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_HOME, KEY_END = 276, 275, 273, 274, 278, 279
KEY_SPACE, KEY_TAB, KEY_ESCAPE, KEY_T = 32, 9, 27, 116
PANEL_RATIO = 0.4  # The smallest part of the width for the panel on the right.


class ViewerScreen(BoxLayout):
    """The screen that shows a game move by move."""

    def __init__(
        self,
        folder: Path | None,
        on_back: Callable[[], None],
        back_label: str = "back_to_top",
        models: Models = Models(),
        **kwargs,
    ):
        """Make the screen. Call open_game to show a game at once.

        Args:
            folder: The games folder, to choose games from (the dialog opens at once); None for a
                screen without the "choose a game" button (when it is opened on one game).
            on_back: Called by the back button (the screen is closed first, see close).
            back_label: The key of the text of the back button (see gui.texts).
            models: KataGo with the main model (the territory and the standing) and with the
                comparison model (its best sequence), each None if it cannot be used.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="horizontal", **kwargs)
        self.record: GameRecord | None = None
        self.browse = viewer_model.Browse()
        self.analyses = GameAnalyses(models, self, in_main_thread)  # KataGo's sequences and standings of the game.
        self.showing_standing = False  # True while the territory and the standing are shown (T).
        self._folder = folder
        self._on_back = on_back
        self._back_label = back_label
        self._moving_slider = False
        self.board = BoardWidget(size_hint_x=None)
        self.add_widget(self.board)
        self.add_widget(self._panel())
        self.bind(size=self._fit_board)
        Window.bind(on_key_down=self._on_key_down)
        self._show()
        if folder is not None:
            in_main_thread(self.choose_game)()  # When the screen has been put in the window.

    def choose_game(self) -> None:
        """Open the dialog that lists the games (only when the screen has a games folder)."""
        if self._folder is not None:
            GameChooser(self._folder, self.open_game).open()

    def open_game(self, path: Path, position: int | None = None) -> None:
        """Read a game in the background and show it, at the first position or at the given one."""
        self.record = None
        self.file_row.set_name(path.name)
        set_text(self.position_label, texts.lazy("viewer_loading"))

        def work() -> None:
            try:
                record = read_game_record(sgf.load_game(path))
            except Exception as error:  # A broken file is told, and the screen stays usable.
                in_main_thread(self._failed)(str(error) or type(error).__name__)
                return
            in_main_thread(self._opened)(record, position)

        threading.Thread(target=work, daemon=True).start()

    @property
    def position(self) -> int:
        """The position of the game that is shown (or in place of whose move a sequence is shown)."""
        return self.browse.position

    def go(self, position: int | None) -> None:
        """Show another position of the game (None does nothing, for a jump that has nowhere to go)."""
        if self.record is None or position is None:
            return
        self.browse = viewer_model.go_to(self.record, position)
        self.showing_standing = False
        self._show()

    def _move(self, change: Callable[[GameRecord, viewer_model.Browse], viewer_model.Browse]) -> None:
        """Change where the screen is with a function of viewer_model, and show it."""
        if self.record is not None:
            self.browse = change(self.record, self.browse)
            self.showing_standing = False
            self._show()

    def next_variation(self) -> None:
        """Switch between the game and the sequences at the move (see viewer_model.next_variation).

        After the last sequence, the comparison model analyzes the move (see the module
        docstring); not while it is analyzing.
        """
        record = self.record
        if record is None or self.analyses.analyzing is not None:
            return
        if not self._may_ask_compare(record):
            self._move(self._next_sequence)
            return
        set_text(self.variation_label, texts.lazy("compare_running"))
        self.analyses.compare(self.position)

    def _next_sequence(self, record: GameRecord, browse: viewer_model.Browse) -> viewer_model.Browse:
        """Return where Tab goes, with the comparison model's sequences of this game."""
        return viewer_model.next_variation(record, browse, self.analyses.lines)

    def _may_ask_compare(self, record: GameRecord) -> bool:
        """True when Tab should start the comparison model: it can be asked at the move, and Tab is at the end."""
        lines = self.analyses.lines
        return self.analyses.can_compare(self.position) and viewer_model.is_last_sequence(record, self.browse, lines)

    def compared(self, position: int) -> None:
        """Show the comparison model's sequence from its first move, if the screen is still at its move."""
        if self.position == position:
            last = len(viewer_model.variations_at(self.record, position, self.analyses.lines)) - 1
            self.browse = viewer_model.Browse(position, last, 1)
        self._show()

    def estimated(self, key: viewer_model.Browse) -> None:
        """Show the territory and the standing, if the screen still shows that end of a sequence."""
        self.showing_standing = self.browse == key
        self._show()

    def failed(self, text_key: str, reason: str) -> None:
        """Tell that KataGo could not calculate something (see viewer.analyses)."""
        show_message(texts.text("error_title"), texts.text(text_key, reason=reason))
        self._show()

    def toggle_standing(self) -> None:
        """Show or hide the territory and the standing at the end of the shown sequence (T).

        They can be shown only when a sequence is shown to its last move. They are calculated
        with the model of the sequence (the comparison model for its own sequence, else the
        main model) the first time, and kept.
        """
        record = self.record
        if record is None or self.analyses.busy:
            return
        if self.showing_standing:
            self.showing_standing = False
            self._show()
            return
        variation = viewer_model.sequence_at_end(record, self.browse, self.analyses.lines)
        if variation is None:
            show_message(texts.text("mode_viewer"), texts.text("estimate_not_here"))
        elif self.browse in self.analyses.standings:
            self.showing_standing = True
            self._show()
        else:
            self._estimate(variation)

    def _estimate(self, variation: Variation) -> None:
        """Ask KataGo for the territory and the standing at the end of the shown sequence."""
        set_text(self.variation_label, texts.lazy("estimate_running"))
        self.analyses.estimate(self.browse, self.position, variation)

    def main_line(self) -> None:
        """Return from a sequence to the game."""
        self.go(self.position)

    def close(self) -> None:
        """Stop taking the keys. Call this before the screen is removed."""
        Window.unbind(on_key_down=self._on_key_down)

    def _panel(self) -> BoxLayout:
        """Make the right panel: the texts, the buttons and the slider."""
        panel = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        set_background(panel, theme.BOX_BACKGROUND_COLOR)
        self.position_label = fitting_label(dp(28), halign="center")
        self.loss_label = fitting_label(dp(28), halign="center")
        self.comment_label = growing_label()
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.comment_label)
        self.slider = Slider(min=0, max=1, step=1, size_hint_y=None, height=dp(36))
        self.slider.bind(value=self._on_slider)
        self.variation_label = fitting_label(dp(28))
        self.file_row = FileNameRow()
        widgets = [
            self.file_row,
            self.position_label,
            self.loss_label,
            self.slider,
            *self._button_rows(),
            self.variation_label,
            scroll,
        ]
        if self._folder is not None:
            widgets.insert(
                0, flat_button(texts.lazy("viewer_choose"), self.choose_game, size_hint_y=None, height=dp(44))
            )
        for widget in widgets:
            panel.add_widget(widget)
        panel.add_widget(flat_button(texts.lazy(self._back_label), self._back, size_hint_y=None, height=dp(44)))
        return panel

    def _button_rows(self) -> list[BoxLayout]:
        """Make the rows of the buttons that move through the game."""
        rows = [
            [
                ("viewer_first", lambda: self.go(0)),
                ("back", lambda: self._step(-1)),
                ("forward", lambda: self._step(1)),
                ("viewer_last", lambda: self.go(self.record.last_position if self.record else None)),
            ],
            [
                ("viewer_previous_ai", lambda: self._jump(previous_ai_position)),
                ("viewer_next_ai", lambda: self._jump(next_ai_position)),
                ("viewer_review", self._show_review),
            ],
            [
                ("viewer_switch", self.next_variation),
                ("viewer_main_line", self.main_line),
                ("estimate_button", self.toggle_standing),
            ],
        ]
        boxes = []
        for buttons in rows:
            box = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            for key, action in buttons:
                box.add_widget(flat_button(texts.lazy(key), action))
            boxes.append(box)
        return boxes

    def _opened(self, record: GameRecord, position: int | None) -> None:
        """Show a game that has been read."""
        self.record = record
        self.browse = viewer_model.Browse()
        self.analyses.open(record)
        self.slider.max = max(record.last_position, 1)
        self.go(position if position is not None else 0)

    def _failed(self, reason: str) -> None:
        """Tell that a game could not be read."""
        set_text(self.position_label, str)
        show_message(texts.text("error_title"), texts.text("viewer_load_failed", reason=reason))

    def _show(self) -> None:
        """Show the board, the texts and the slider for the current position."""
        record = self.record
        if record is None:
            self.board.show(None)
            set_text(self.position_label, texts.lazy("viewer_choose_game"))
            for label in (self.loss_label, self.comment_label, self.variation_label):
                set_text(label, str)
            return
        browse = self.browse
        position = browse.position
        added = dict(self.analyses.lines)
        standing = self.analyses.standings.get(browse) if self.showing_standing else None
        view = viewer_model.browse_view(record, browse, added)
        self.board.show(replace(view, ownership=standing.end.ownership) if standing is not None else view)
        set_text(self.position_label, lambda: viewer_model.position_text(record, position))
        set_text(self.loss_label, lambda: viewer_model.loss_text(record, position))
        set_text(self.variation_label, lambda: self._variation_text(record, browse, added, standing))
        set_text(self.comment_label, lambda: viewer_model.browse_comment_text(record, browse, added))
        self._moving_slider = True
        self.slider.value = position
        self._moving_slider = False

    @staticmethod
    def _variation_text(record: GameRecord, browse: viewer_model.Browse, added: dict, standing: Standing | None) -> str:
        """Return the text about the shown sequence, with the standing at its end when it is shown."""
        text = viewer_model.variation_text(record, browse, added)
        return f"{text}\n{texts.standing_text(standing, browse.step)}" if standing is not None else text

    def _step(self, step: int) -> None:
        """Move some moves forward (or back, if step is negative) through the game, or through the shown sequence."""
        self._move(lambda record, browse: viewer_model.step_game(record, browse, step, self.analyses.lines))

    def _jump(self, find: Callable[[GameRecord, int], int | None]) -> None:
        """Go to the previous or next move with an AI commentary (find is previous_ai_position or next_ai_position)."""
        if self.record is not None:
            self.go(find(self.record, self.position))

    def _show_review(self) -> None:
        """Show the AI review of the whole game in a dialog."""
        if self.record is None:
            return
        review = review_text(self.record)
        if review:
            show_long_message(texts.text("viewer_review"), review)
        else:
            show_message(texts.text("viewer_review"), texts.text("viewer_no_review"))

    def _on_slider(self, _slider, value: float) -> None:
        """Go to the position chosen with the slider (not when the slider is moved by _show)."""
        if not self._moving_slider:
            self.go(int(value))

    def _fit_board(self, *_args) -> None:
        """Make the board as wide as the screen is tall, but leave room for the panels."""
        self.board.width = min(self.height, self.width * (1 - PANEL_RATIO))

    def _back(self) -> None:
        """Close the screen and go back."""
        self.close()
        self._on_back()

    def _on_key_down(self, _window, key: int, _scancode, _text, modifiers: list[str]) -> bool:
        """Move through the game and the sequences with the keys (only when no dialog is open over this screen)."""
        if not Window.children or self not in Window.children[0].walk():
            return False
        action = self._variation_key(key, "shift" in modifiers) or self._game_key(key)
        if action is None:
            return False
        action()
        return True

    def _variation_key(self, key: int, shift: bool) -> Callable[[], None] | None:
        """Return what Space, Tab and Esc do, or None for other keys (Space moves like ← →)."""
        if key == KEY_SPACE:
            return (lambda: self._step(-1)) if shift else (lambda: self._step(1))
        actions = {KEY_TAB: self.next_variation, KEY_ESCAPE: self.main_line, KEY_T: self.toggle_standing}
        return actions.get(key)

    def _game_key(self, key: int) -> Callable[[], None] | None:
        """Return what a key does to move through the game (← → also through the shown sequence), or None."""
        actions = {
            KEY_LEFT: lambda: self._step(-1),
            KEY_RIGHT: lambda: self._step(1),
            KEY_UP: lambda: self._jump(previous_ai_position),
            KEY_DOWN: lambda: self._jump(next_ai_position),
            KEY_HOME: lambda: self.go(0),
            KEY_END: lambda: self.go(self.record.last_position if self.record else None),
        }
        return actions.get(key)
