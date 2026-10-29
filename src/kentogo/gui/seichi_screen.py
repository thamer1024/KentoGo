"""The screen of the territory counting practice (seichi): the board on the left, information on the right.

It shows the final position of a game that ended by counting, and the user
arranges the stones by dragging them (see editable_board). The board is made by
a function given to the screen (make_board), so that another board can be used
without changing the rest of the screen. When the board can take back changes
(undo and reset), the panel has buttons for them.

The panel shows the territory of each player (Japanese rules). A move that would
change it is refused, and a warning dialog tells why. Below it are the trays of
prisoners: the user drags prisoners onto the territory of their color, and the
"take off the dead stones" button puts the dead stones in the trays. The "computer's
seichi" button does all of it as the computer would (see seichi.auto_fill), and
plays its steps at once. After it, the steps of the computer's seichi can be shown one at a
time with the buttons below the trays, or with the left and right arrow keys (the
stones cannot be moved while a step before the last is shown). Going forward, the stones
of the step slide to their points as if a person moved them, also prisoners from their
tray (see gui.step_motion); the time comes from settings.json (seichi_step_seconds).
Pressing a key or a button while they move puts them at once. The "play" button shows the
steps one after another until the last one; pressing it again, or any step key or
button, stops it.

So that the screen fits a small window, the panel shows only the buttons that can be used now
(see _usable_buttons), in two columns in the same place: for example "確認" only when the end
can be confirmed, and "できた" and "できなかった" only after the seichi is ended or the
computer has done it.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

from kentogo.common.types import Position
from kentogo.gui import texts, theme
from kentogo.gui.board_view import make_board_view
from kentogo.gui.board_widget import BoardWidget
from kentogo.gui.dialogs import show_message
from kentogo.gui.editable_board import EditableBoard
from kentogo.gui.file_name_row import FileNameRow
from kentogo.gui.prisoner_tray import PrisonerTray
from kentogo.gui.step_motion import step_motions
from kentogo.gui.widgets import fitting_label, flat_button, in_main_thread, set_background, set_text
from kentogo.seichi.arrangement import AutoPlan, PlacementError, TerritoryChangedError
from kentogo.seichi.count_check import CountCheck
from kentogo.seichi.final_position import FinishedGame
from kentogo.seichi.seichi_settings import STEP_SECONDS

# The part of the width that is kept for the panel at least, as on the quiz screen.
MIN_PANEL_RATIO = 0.3

# The arrow keys that show the steps of the computer's seichi (Kivy's key codes).
KEY_LEFT = 276
KEY_RIGHT = 275

# The pause between two steps when they are played one after another (at least this, in seconds).
PLAY_PAUSE = 0.25

BUTTON_HEIGHT = 40  # dp
SPACING = 6  # dp

# Makes the board widget for a position.
BoardMaker = Callable[[Position], Widget]


def view_only_board(position: Position) -> Widget:
    """Make a board that only shows a position (the stones cannot be moved)."""
    board = BoardWidget()
    board.show(make_board_view(position))
    return board


def arranging_board(position: Position) -> Widget:
    """Make a board whose stones the user drags to arrange the territory."""
    return EditableBoard(position, when_refused=warn_territory_changed)


def warn_territory_changed(refused: TerritoryChangedError) -> None:
    """Warn that a move would have changed the territory, and was taken back."""
    before, after = refused.before, refused.after
    message = texts.text(
        "seichi_refused", black=before.black, white=before.white, new_black=after.black, new_white=after.white
    )
    show_message(texts.text("seichi_warning"), message)


class SeichiScreen(BoxLayout):
    """The territory counting screen for one game."""

    def __init__(
        self,
        game: FinishedGame,
        on_back: Callable[[], None],
        make_board: BoardMaker = arranging_board,
        on_judged: Callable[[bool], None] | None = None,
        progress: Callable[[], str] | None = None,
        step_seconds: float = STEP_SECONDS,
        **kwargs,
    ):
        """Make the screen.

        Args:
            game: The game to count.
            on_back: Called when the user goes back to choosing the practice.
            make_board: Makes the board for the final position. Replace it to let the user move stones.
            on_judged: Called with True ("できた") or False ("できなかった") when the user says how the
                counting went; the next game is shown then. Without it, the buttons are not shown.
            progress: Makes a line about this game, such as "今回 2 / 3 局目（復習）", or None.
            step_seconds: How long a stone takes to move when a step of the computer's seichi is shown.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="horizontal", **kwargs)
        self.game = game
        self.board = make_board(game.position)
        self.board.size_hint_x = None
        self.trays: list[PrisonerTray] = []
        self.steps = None  # The steps of the computer's seichi (FillResult), while they can be shown.
        self.step_number = 0
        self.step_seconds = step_seconds
        self.checked: CountCheck | None = None  # The check of the user's seichi and counting (整地終了).
        self._playing = False  # True while the steps are played one after another.
        self._play_event = None  # The timer of the next step while they are played.
        if isinstance(self.board, EditableBoard):
            self.board.when_changed = self._refresh
            self.board.when_not_allowed = self._not_allowed
            # Black stones captured by white, and white stones captured by black.
            self.trays = [PrisonerTray(color, self._drop) for color in "BW"]
            for tray in self.trays:
                set_text(tray, texts.lazy(f"seichi_tray_{tray.color}"), "title")
        self.add_widget(self.board)
        self.bind(size=self._fit_board)
        self._on_back = on_back
        self._on_judged = on_judged
        self._progress = progress
        self._buttons = self._make_buttons()
        self.add_widget(self._panel(self._leave))
        self._refresh()
        Window.bind(on_key_down=self._on_key_down)

    def _leave(self) -> None:
        """Stop listening to the keys, and go back to choosing the practice."""
        self._stop_playing()
        Window.unbind(on_key_down=self._on_key_down)
        self._on_back()

    def _judge(self, good: bool) -> None:
        """Stop listening to the keys, and tell how the counting went (the next game comes then)."""
        self._stop_playing()
        Window.unbind(on_key_down=self._on_key_down)
        self._on_judged(good)

    def _on_key_down(self, _window, key: int, _scancode, _text, _modifiers) -> bool:
        """The right arrow shows the next step of the computer's seichi, and the left arrow the one before.

        The keys are not used while a dialog is open, while the computer is thinking, or when
        there are no steps to show.
        """
        if key not in (KEY_LEFT, KEY_RIGHT) or self.steps is None or self.disabled:
            return False
        if any(isinstance(widget, ModalView) for widget in Window.children):
            return False
        self._user_step(1 if key == KEY_RIGHT else -1)
        return True

    def _panel(self, on_back: Callable[[], None]) -> BoxLayout:
        """Make the panel on the right: the game, the territory, the trays of prisoners, and the buttons."""
        panel = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(SPACING))
        set_background(panel, theme.BOX_BACKGROUND_COLOR)
        info = fitting_label(dp(48))
        set_text(info, self._info_text)
        panel.add_widget(info)
        file_row = FileNameRow()
        file_row.set_name(self.game.path.name)
        panel.add_widget(file_row)
        self.territory_label = fitting_label(dp(30))
        panel.add_widget(self.territory_label)
        self.status_label = fitting_label(dp(24))
        panel.add_widget(self.status_label)
        for tray in self.trays:
            panel.add_widget(tray)
        if isinstance(self.board, EditableBoard):
            panel.add_widget(self._step_box())
        panel.add_widget(Widget())  # Space, so that the buttons stay at the bottom.
        self.button_grid = GridLayout(
            cols=2, size_hint_y=None, spacing=dp(SPACING), row_default_height=dp(BUTTON_HEIGHT)
        )
        panel.add_widget(self.button_grid)
        back = flat_button(texts.lazy("back_to_top"), on_back, size_hint_y=None, height=dp(BUTTON_HEIGHT))
        panel.add_widget(back)
        return panel

    def _info_text(self) -> str:
        """Return the text about the game: its name, its result, the number of moves, and the progress."""
        result = self.game.result or texts.text("seichi_no_result")
        info = texts.text("seichi_info", name=self.game.path.stem, result=result, moves=len(self.game.position.moves))
        return f"{info}\n{self._progress()}" if self._progress else info

    def _make_buttons(self) -> dict:
        """Make the buttons of the panel, by name (only those that can be used are put in the panel)."""
        buttons = {}
        if isinstance(self.board, EditableBoard):
            for name, action in (
                ("seichi_remove_dead", self.board.remove_dead),
                ("seichi_confirm", self._confirm),
                ("seichi_finish", self._finish),
                ("seichi_auto", self._auto_fill),
                ("seichi_undo", self.board.undo),
                ("seichi_reset", self.board.reset),
            ):
                buttons[name] = flat_button(texts.lazy(name), action)
        if self._on_judged is not None:
            buttons["seichi_good"] = flat_button(texts.lazy("seichi_good"), lambda: self._judge(True))
            buttons["seichi_bad"] = flat_button(texts.lazy("seichi_bad"), lambda: self._judge(False))
        for button in buttons.values():
            _wrap_text(button)
        return buttons

    def _usable_buttons(self, arrangement) -> list[str]:
        """Return the names of the buttons that can be used now, in the order of the panel."""
        usable = {
            "seichi_remove_dead": not arrangement.in_seichi and bool(arrangement.dead),
            "seichi_confirm": arrangement.ready_to_confirm,
            "seichi_finish": arrangement.in_seichi and not arrangement.auto_done and self.checked is None,
            "seichi_auto": arrangement.ready_for_auto,
            "seichi_good": self.checked is not None or arrangement.auto_done,
            "seichi_bad": self.checked is not None or arrangement.auto_done,
            "seichi_undo": arrangement.can_undo,
            "seichi_reset": arrangement.can_undo,
        }
        return [name for name in self._buttons if usable.get(name)]

    def _show_buttons(self, names: list[str]) -> None:
        """Put the buttons with these names into the panel, two in a row, and take the others out."""
        grid = self.button_grid
        if [child for child in reversed(grid.children)] == [self._buttons[name] for name in names]:
            return
        grid.clear_widgets()
        for name in names:
            grid.add_widget(self._buttons[name])
        rows = (len(names) + 1) // 2
        grid.height = rows * dp(BUTTON_HEIGHT) + max(0, rows - 1) * dp(SPACING)

    def _step_box(self) -> BoxLayout:
        """Make the place of the line and the buttons that show the computer's seichi one step at a time.

        The place is empty at first: the line and the buttons are put into it only when they are
        shown. (Hidden widgets that stay in the panel would still catch the clicks on the tray above
        them, so that its stones could not be picked up.)
        """
        self.step_holder = BoxLayout(size_hint_y=None, height=0)
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.step_label = fitting_label(dp(48))
        # When the line wraps, the box grows with it (while it is shown).
        self.step_label.bind(height=lambda *_: self._show_step_box(self.steps is not None))
        box.add_widget(self.step_label)
        row = BoxLayout(spacing=dp(4), size_hint_y=None, height=dp(40))
        for key, change in (("first", -(10**6)), ("back", -1), ("forward", 1), ("last", 10**6)):
            row.add_widget(flat_button(texts.lazy(f"seichi_steps_{key}"), lambda c=change: self._user_step(c)))
        box.add_widget(row)
        self.play_button = flat_button(texts.lazy("seichi_steps_play"), self.toggle_play, size_hint_y=None)
        self.play_button.height = dp(40)
        box.add_widget(self.play_button)
        self.step_box = box
        return self.step_holder

    def _user_step(self, change: int) -> None:
        """Show another step because the user asked (a key or a button): this stops playing the steps."""
        self._stop_playing()
        self._go_step(change)

    def _go_step(self, change: int) -> None:
        """Show another step of the computer's seichi (the last step is the board as it is now).

        One step forward is shown with its stones sliding to their points. Stones that are still
        moving from the step before are put at once first.
        """
        if self.steps is None:
            return
        self.board.finish_animation()
        total = len(self.steps.steps)
        previous = self.step_number
        self.step_number = max(0, min(total, self.step_number + change))
        shown = self.steps.steps[self.step_number - 1] if self.step_number else None
        number = self.step_number
        set_text(self.step_label, lambda: texts.fill_step_text(shown, number, total))
        self._show_step_prisoners()
        if shown is None or self.step_number != previous + 1:
            self._step_shown()
            return
        motions = step_motions(shown)
        self.board.animate_step(
            shown.stones, shown.points, motions, self.step_seconds, self._tray_position, self._step_shown
        )

    def _step_shown(self) -> None:
        """Show the board of the current step (after its stones have moved), and go on if the steps are played."""
        self._show_step_board()
        if self._playing:
            pause = max(PLAY_PAUSE, self.step_seconds / 2)
            self._play_event = Clock.schedule_once(lambda _dt: self._play_next(), pause)

    def _show_step_board(self) -> None:
        """Show the stones of the current step on the board."""
        if self.step_number == len(self.steps.steps):
            self.board.end_steps()
        elif self.step_number == 0:
            self.board.show_step(self.steps.start, ())
        else:
            step = self.steps.steps[self.step_number - 1]
            self.board.show_step(step.stones, step.points)

    def _show_step_prisoners(self) -> None:
        """Show in the trays the prisoners of the current step (a prisoner leaves its tray when its step starts).

        While a step before the last is shown, the prisoners cannot be picked up (they are not the trays now).
        """
        if self.step_number == 0:
            prisoners = self.steps.start_prisoners
        else:
            prisoners = self.steps.steps[self.step_number - 1].prisoners
        for tray in self.trays:
            tray.show(prisoners.get(tray.color, 0))
            tray.disabled = self.step_number < len(self.steps.steps)

    def toggle_play(self) -> None:
        """Play the steps one after another to the last one (from the start, if the last one is shown), or stop."""
        if self._playing:
            self._stop_playing()
            return
        if self.steps is None:
            return
        if self.step_number >= len(self.steps.steps):
            self._go_step(-(10**6))
        self._playing = True
        set_text(self.play_button, texts.lazy("seichi_steps_stop"))
        self._play_next()

    def _play_next(self) -> None:
        """Show the next step while the steps are played, and stop after the last one."""
        self._play_event = None
        if not self._playing or self.steps is None:
            return
        if self.step_number >= len(self.steps.steps):
            self._stop_playing()
            return
        self._go_step(1)

    def _stop_playing(self) -> None:
        """Stop playing the steps (the step shown stays)."""
        self._playing = False
        if self._play_event is not None:
            self._play_event.cancel()
            self._play_event = None
        if getattr(self, "play_button", None) is not None:
            set_text(self.play_button, texts.lazy("seichi_steps_play"))

    def _tray_position(self, color: str) -> tuple[float, float]:
        """Return where the stones of a tray of prisoners are, in window coordinates (prisoners slide from there)."""
        tray = next((tray for tray in self.trays if tray.color == color), None)
        if tray is None:
            return self.board.to_window(*self.board.center)
        return tray.to_window(*tray.stone_center())

    def _leave_steps(self, auto_done: bool) -> None:
        """After a change of the board, show the stones now (and forget the steps if auto_fill was taken back)."""
        if self.steps is None:
            return
        self._stop_playing()
        if not auto_done:
            self.steps = None
            self.board.end_steps()
            self._show_step_box(False)
            for tray in self.trays:
                tray.disabled = False
        elif self.step_number < len(self.steps.steps):
            self._go_step(len(self.steps.steps))

    def _show_step_box(self, shown: bool) -> None:
        """Show or hide the step buttons (they are taken out of the panel while hidden)."""
        if shown:
            if self.step_box.parent is None:
                self.step_holder.add_widget(self.step_box)
            self.step_box.height = self.step_label.height + dp(88)
            self.step_holder.height = self.step_box.height
        else:
            if self.step_box.parent is not None:
                self.step_holder.remove_widget(self.step_box)
            self.step_holder.height = 0

    def _refresh(self) -> None:
        """Show the territory and the prisoners now (only for a board whose stones can be arranged)."""
        arrangement = getattr(self.board, "arrangement", None)
        if arrangement is None:
            set_text(self.territory_label, str)
            set_text(self.status_label, str)
            self._show_buttons([])
            return
        set_text(self.territory_label, lambda: self._territory_text(arrangement))
        prisoners = arrangement.prisoners
        for tray in self.trays:
            tray.show(prisoners[tray.color])
        self._leave_steps(arrangement.auto_done)
        # For example, the computer does the rest only after the user has taken off the dead stones and filled the dame.
        self._show_buttons(self._usable_buttons(arrangement))
        if arrangement.in_seichi:
            status = "seichi_in_seichi"
        else:
            status = "seichi_ready" if arrangement.ready_to_confirm else "seichi_not_ready"
        set_text(self.status_label, texts.lazy(status))

    def _counts_hidden(self, arrangement) -> bool:
        """True while the user practices: the numbers are shown only after 整地終了 (or the computer's seichi)."""
        return self._on_judged is not None and self.checked is None and not arrangement.auto_done

    def _territory_text(self, arrangement) -> str:
        """Return the lines about the territory now, the points that are not territory, and the prisoners.

        While the user practices counting (see _counts_hidden), the numbers are not shown.
        """
        count = arrangement.territory
        confirmed = arrangement.confirmed_count
        if self._counts_hidden(arrangement):
            territory = texts.text("seichi_counts_hidden")
        elif confirmed is None:
            territory = texts.text("seichi_territory", black=count.black, white=count.white)
        else:
            territory = texts.text(
                "seichi_territory_now",
                black=count.black,
                white=count.white,
                confirmed_black=confirmed.black,
                confirmed_white=confirmed.white,
            )
            undecided = arrangement.undecided
            if undecided:
                territory += texts.text("seichi_undecided", count=len(undecided))
        if arrangement.neutral:
            territory += texts.text("seichi_seki", count=len(arrangement.neutral))
        return territory + self._prisoner_text(arrangement)

    def _prisoner_text(self, arrangement) -> str:
        """Return the lines about the prisoners of the dead stones, and the lead that the seichi keeps."""
        lines = ""
        pending, trays = arrangement.pending_prisoners, arrangement.prisoners
        if any(pending.values()):
            lines += texts.text(
                "seichi_dead_pending",
                black=pending["B"],
                white=pending["W"],
                black_total=trays["B"] + pending["B"],
                white_total=trays["W"] + pending["W"],
            )
        if self._counts_hidden(arrangement):
            return lines
        margin = arrangement.margin
        komi = self.game.position.komi
        lines += texts.text("seichi_margin", lead=texts.lead_text(margin), result=texts.lead_text(margin - komi, komi))
        return lines

    def _confirm(self) -> None:
        """Confirm the end of the game: from then on the stones may be moved freely (the seichi phase)."""
        try:
            self.board.arrangement.confirm()
        except PlacementError as refused:
            self._not_allowed(str(refused))
            return
        self.board.refresh()
        self._refresh()

    def _finish(self) -> None:
        """End the user's seichi: check it, and show the result (整地終了).

        Nothing is recorded here: a seichi with the right numbers may still not be neat, so the
        user records how it went with "できた" or "できなかった".
        """
        if not self.board.arrangement.in_seichi or self.checked is not None:
            return
        try:
            check = self.board.arrangement.check_count()
        except PlacementError as refused:
            self._not_allowed(str(refused))
            return
        self.checked = check
        self._refresh()
        message = texts.count_check_text(check, self.game.position.komi)
        show_message(texts.text("count_result_title"), message)

    def _not_allowed(self, key: str) -> None:
        """Tell why a click on the board was not allowed (for example a dame that would be captured)."""
        show_message(texts.text("seichi_warning"), texts.text(key))

    def _auto_fill(self) -> None:
        """Let the computer find its seichi in a background thread (it takes a few seconds).

        While it thinks, the screen cannot be used, and the seconds are shown.
        """
        arrangement = self.board.arrangement
        if not arrangement.ready_for_auto:
            self._not_allowed("auto_not_ready")
            return
        self.disabled = True
        self._thinking_since = time.monotonic()
        self._thinking_timer = Clock.schedule_interval(self._show_thinking, 0.5)
        self._show_thinking()

        def work() -> None:
            """Plan the seichi; the board is changed later, in the main thread."""
            try:
                plan = arrangement.plan_auto()
            except PlacementError as refused:  # For example a stone would be left in the other territory.
                in_main_thread(self._auto_refused)(str(refused))
                return
            except Exception as error:  # For example a position the planner cannot handle.
                in_main_thread(self._auto_failed)(str(error))
                return
            in_main_thread(self._auto_planned)(plan)

        threading.Thread(target=work, daemon=True).start()

    def _show_thinking(self, *_args) -> None:
        """Show how long the computer has been thinking."""
        seconds = int(time.monotonic() - self._thinking_since)
        set_text(self.status_label, texts.lazy("seichi_thinking", seconds=seconds))

    def _stop_thinking(self) -> None:
        """Make the screen usable again."""
        self._thinking_timer.cancel()
        self.disabled = False
        self._refresh()

    def _auto_refused(self, key: str) -> None:
        """Tell why the computer did not make its seichi (the key of a screen text)."""
        self._stop_thinking()
        self._not_allowed(key)

    def _auto_failed(self, message: str) -> None:
        """Tell that the computer could not find its seichi."""
        self._stop_thinking()
        show_message(texts.text("error_title"), texts.text("seichi_auto_failed", detail=message))

    def _auto_planned(self, plan: AutoPlan) -> None:
        """Put the computer's seichi on the board, and play its steps from the first one (undo takes it back).

        The stones slide to their points step by step; the count is shown in the panel.
        """
        self._stop_thinking()
        if not self.board.use_auto(plan):
            return  # The stones changed while it was thinking (it cannot happen while the screen is disabled).
        result = plan.result
        if result.steps:
            self.steps = result
            self.step_number = 0
            self._go_step(0)
            self._show_step_box(True)
            self.toggle_play()

    def _drop(self, color: str, position: tuple[float, float], count: int) -> None:
        """Put prisoners dropped from a tray on the board.

        Those that cannot go there (no room, or not that color's territory) go back to the tray
        without a word.
        """
        with contextlib.suppress(PlacementError):
            self.board.drop_prisoners(color, position, count)

    def _fit_board(self, *_args) -> None:
        """Make the board as wide as the screen is tall, but leave at least MIN_PANEL_RATIO for the panel."""
        self.board.width = min(self.height, self.width * (1 - MIN_PANEL_RATIO))


def _wrap_text(button) -> None:
    """Let a long text of a button wrap at its width (the buttons are half as wide as the panel)."""
    button.halign = "center"
    button.bind(width=lambda widget, width: setattr(widget, "text_size", (width - dp(8), None)))
