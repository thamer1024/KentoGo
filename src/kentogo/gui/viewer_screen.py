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

T (or its button) turns the territory and the standing on, and T again turns them off; they stay on
when the user moves or goes to the next sequence, and the button tells whether they are on. While
they are on, every position shown (of the game or of a sequence) gets its areas on the board and a
rough standing, from a shallow reading with the main model (see katago.quick_reading). At the last
move of a sequence, the exact territory and standing are shown instead, as KaTrain does, with how
much better the sequence is than the game after the same number of moves (see katago.estimate):
they are calculated the first time with the main model and kept.

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
from kentogo.common.types import Position
from kentogo.gui import texts, theme, viewer_model
from kentogo.gui.board_widget import BoardWidget
from kentogo.gui.dialogs import show_long_message, show_message
from kentogo.gui.file_name_row import FileNameRow
from kentogo.gui.game_chooser import GameChooser
from kentogo.gui.widgets import fitting_label, flat_button, growing_label, in_main_thread, set_background, set_text
from kentogo.katago.estimate import Standing, played
from kentogo.katago.evaluate import Models
from kentogo.katago.quick_reading import QuickReading, QuickReadings
from kentogo.record.game_record import (
    GameRecord,
    next_ai_position,
    previous_ai_position,
    read_game_record,
    review_text,
)
from kentogo.viewer.analyses import ESTIMATE_FAILED, NO_ENGINE, GameAnalyses

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
            models: KataGo with the main model (the territory and the standing), None if it cannot be used.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="horizontal", **kwargs)
        self.record: GameRecord | None = None
        self.browse = viewer_model.Browse()
        self.analyses = GameAnalyses(models, self, in_main_thread)  # KataGo's standings of the game.
        self.standing_on = False  # True while the territory and the standing are turned on (T).
        self.standing_button = None  # The button of T, which tells whether they are on.
        self._estimating: viewer_model.Browse | None = None  # The end of a sequence whose standing is calculated.
        self._standing_failed: set[viewer_model.Browse] = set()  # Ends whose standing could not be calculated.
        self.quick = QuickReadings(in_main_thread)  # The shallow areas of the positions shown (while on).
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
        self._show()

    def _move(self, change: Callable[[GameRecord, viewer_model.Browse], viewer_model.Browse]) -> None:
        """Change where the screen is with a function of viewer_model, and show it."""
        if self.record is not None:
            self.browse = change(self.record, self.browse)
            self._show()

    def next_variation(self) -> None:
        """Switch between the game and the sequences at the move (see viewer_model.next_variation)."""
        self._move(viewer_model.next_variation)

    def estimated(self, key: viewer_model.Browse) -> None:
        """Show the territory and the standing, if the screen still shows that end of a sequence."""
        self._estimating = None
        self._show()

    def failed(self, text_key: str, reason: str) -> None:
        """Tell that KataGo could not calculate something (see viewer.analyses).

        A standing that cannot be calculated is not asked again; without KataGo, the standings are turned off.
        """
        if text_key == ESTIMATE_FAILED and self._estimating is not None:
            self._standing_failed.add(self._estimating)
        if text_key == NO_ENGINE:
            self._set_standing_on(False)
        self._estimating = None
        show_message(texts.text("error_title"), texts.text(text_key, reason=reason))
        self._show()

    def toggle_standing(self) -> None:
        """Turn the territory and the standing on or off (T); while on, they are shown at the end of every sequence."""
        self._set_standing_on(not self.standing_on)
        if not self.standing_on:
            self.quick.stop()
        self._show()

    def _set_standing_on(self, on: bool) -> None:
        """Keep whether the territory and the standing are on, and tell it on the button."""
        self.standing_on = on
        if self.standing_button is not None:
            set_text(self.standing_button, texts.lazy("estimate_button_on" if on else "estimate_button"))

    def _ensure_standing(self, record: GameRecord, browse: viewer_model.Browse) -> None:
        """While on, ask KataGo for what is not known yet: the exact standing at the last move of a sequence,
        and the shallow areas of any other position shown.

        Only one exact standing is calculated at a time; when it has come, the screen is shown again,
        which asks for the next.
        """
        if not self.standing_on:
            self.quick.stop()
            return
        variation = viewer_model.sequence_at_end(record, browse)
        if variation is None:
            self._ask_quick(record, browse)
            return
        known = browse in self.analyses.standings or browse in self._standing_failed
        if self.analyses.busy or known:
            return
        self._estimating = browse
        set_text(self.variation_label, texts.lazy("estimate_running"))
        self.analyses.estimate(browse, self.position, variation)

    def _ask_quick(self, record: GameRecord, browse: viewer_model.Browse) -> None:
        """Ask the main model for the shallow areas of the shown position (see katago.quick_reading)."""
        main = self.analyses.models.main
        if main is None:
            return
        position = self._position_of(record, browse)
        self.quick.ask(main.engine, browse, position, main.settings.wide_root_noise, self._show)

    def _position_of(self, record: GameRecord, browse: viewer_model.Browse) -> Position:
        """Return the position that the board shows: the game after the move, or the sequence played so far."""
        if browse.variation is None:
            return record.position_after(browse.position)
        variation = viewer_model.variations_at(record, browse.position)[browse.variation]
        return played(record.position_before(browse.position), variation.moves[: browse.step])

    def main_line(self) -> None:
        """Return from a sequence to the game."""
        self.go(self.position)

    def close(self) -> None:
        """Stop taking the keys and the shallow reading. Call this before the screen is removed."""
        self.quick.stop()
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
                button = flat_button(texts.lazy(key), action)
                if key == "estimate_button":
                    self.standing_button = button
                box.add_widget(button)
            boxes.append(box)
        return boxes

    def _opened(self, record: GameRecord, position: int | None) -> None:
        """Show a game that has been read."""
        self.record = record
        self.browse = viewer_model.Browse()
        self.analyses.open(record)
        self._estimating = None
        self._standing_failed = set()
        self.quick.stop()
        self.quick = QuickReadings(in_main_thread)
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
        at_end = viewer_model.sequence_at_end(record, browse) is not None
        standing = self.analyses.standings.get(browse) if self.standing_on and at_end else None
        quick = self.quick.get(browse) if self.standing_on and standing is None else None
        view = viewer_model.browse_view(record, browse)
        areas = standing.end.ownership if standing is not None else quick.ownership if quick is not None else None
        self.board.show(replace(view, ownership=areas) if areas is not None else view)
        set_text(self.position_label, lambda: viewer_model.position_text(record, position))
        set_text(self.loss_label, lambda: viewer_model.loss_text(record, position))
        set_text(self.variation_label, lambda: self._variation_text(record, browse, standing, quick))
        set_text(self.comment_label, lambda: viewer_model.comment_text(record, position))
        self._moving_slider = True
        self.slider.value = position
        self._moving_slider = False
        self._ensure_standing(record, browse)

    @staticmethod
    def _variation_text(
        record: GameRecord,
        browse: viewer_model.Browse,
        standing: Standing | None,
        quick: QuickReading | None,
    ) -> str:
        """Return the text about the shown sequence, with the exact standing at its end or the rough one."""
        text = viewer_model.variation_text(record, browse)
        if standing is not None:
            return f"{text}\n{texts.standing_text(standing, browse.step)}".strip("\n")
        if quick is not None:
            return f"{text}\n{texts.quick_standing_text(quick.lead)}".strip("\n")
        return text

    def _step(self, step: int) -> None:
        """Move some moves forward (or back, if step is negative) through the game, or through the shown sequence."""
        self._move(lambda record, browse: viewer_model.step_game(record, browse, step))

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
