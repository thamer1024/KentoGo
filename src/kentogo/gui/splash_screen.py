"""The start screen: shows the progress of reading the games, then today's numbers.

The games are read in a background thread (see today.load_today), so the
window opens at once even when there are many games. When they have been read,
the screen shows how many new problems and reviews there are today, and the
start button (or Enter) opens the quiz screen. The back button, usable when the games
have been read, goes back to the top screen.

Problems found at the start (for example that KataGo or the comparison model
could not be started) are shown in a dialog, because the user is not expected
to look at the console. The games that gave no problems can be seen with a button.
The flags at the bottom change the language of the screens (see menu.flag_row).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout

from kentogo.gui import texts, theme
from kentogo.gui.dialogs import show_message
from kentogo.gui.menu import flag_row
from kentogo.gui.widgets import flat_button, in_main_thread, set_background, set_text, wrapping_label
from kentogo.notice import Notice
from kentogo.today import Progress, TodayProblems

# Key codes of Kivy.
KEY_ENTERS = (13, 271)


class SplashScreen(AnchorLayout):
    """The start screen.

    Attributes:
        today: Today's problems, or None while the games are being read.
    """

    def __init__(
        self,
        on_start: Callable[[TodayProblems], None],
        notices: tuple[Notice, ...] = (),
        on_back: Callable[[], None] | None = None,
        **kwargs,
    ):
        """Make the screen. Call load() to start reading the games.

        Args:
            on_start: Called with today's problems when the user starts.
            notices: Problems found before the window opened, shown in a dialog at once.
            on_back: Called by the "back to the top screen" button; without it, there is no button.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(anchor_x="center", anchor_y="center", **kwargs)
        self.today: TodayProblems | None = None
        self._on_start = on_start
        box = BoxLayout(orientation="vertical", size_hint=(None, None), size=(dp(520), dp(520)), padding=dp(24))
        box.spacing = dp(12)
        set_background(box, theme.BOX_BACKGROUND_COLOR)
        title = wrapping_label(halign="center", valign="middle", font_size=sp(40))
        set_text(title, texts.lazy("splash_title"))
        title.size_hint_y = None
        title.height = dp(64)
        subtitle = wrapping_label(halign="center", size_hint_y=None)
        set_text(subtitle, texts.lazy("splash_subtitle"))
        subtitle.height = dp(28)
        self.status_label = wrapping_label(halign="center", valign="middle")
        set_text(self.status_label, texts.lazy("splash_preparing"))
        self.start_button = flat_button(texts.lazy("splash_start"), self.start, size_hint_y=None, height=dp(48))
        self.start_button.disabled = True
        self.skipped_button = flat_button(
            texts.lazy("splash_show_skipped"), self.show_skipped, size_hint_y=None, height=dp(40)
        )
        self.skipped_button.opacity = 0  # Shown only when some games gave no problems.
        self.skipped_button.disabled = True
        # The flags of the languages, as in KaTrain's menu: the first start is in English.
        flags = flag_row()
        for widget in (title, subtitle, self.status_label, self.skipped_button, self.start_button, flags):
            box.add_widget(widget)
        self.back_button = None
        if on_back is not None:
            self._on_back = on_back
            self.back_button = flat_button(texts.lazy("back_to_top"), self.back, size_hint_y=None, height=dp(40))
            self.back_button.disabled = True  # Usable when the games have been read (KataGo has started then).
            box.add_widget(self.back_button)
        self.add_widget(box)
        Window.bind(on_key_down=self._on_key_down)
        if notices:
            # Opened a moment later, when the window has been made.
            in_main_thread(lambda: show_message(texts.text("notice_title"), texts.notices_text(notices)))()

    def load(self, load: Callable[[Progress], TodayProblems]) -> None:
        """Read the games in a background thread, showing the progress, then today's numbers.

        Args:
            load: Makes today's problems. It is given a function to report the progress.
        """

        def work() -> None:
            """Run in the background thread. Errors are shown on the screen."""
            try:
                today = load(in_main_thread(self.show_progress))
            except Exception as error:  # The app must still start, so that the settings can be fixed.
                message = Notice("splash_failed", {"reason": error})
                today = TodayProblems([], message, notices=[message])  # Shown in a dialog too, to be copied.
            in_main_thread(self.show_today)(today)

        threading.Thread(target=work, daemon=True).start()

    def show_progress(self, done: int, total: int) -> None:
        """Show how many games have been read (called in the main thread)."""
        if self.today is None:
            set_text(self.status_label, texts.lazy("splash_loading", done=done, total=total))

    def show_today(self, today: TodayProblems) -> None:
        """Show today's numbers, and let the user start (called in the main thread)."""
        self.today = today
        set_text(self.status_label, lambda: _today_text(today))
        self.start_button.disabled = False
        if self.back_button is not None:
            self.back_button.disabled = False
        if today.skipped_games:
            self.skipped_button.opacity = 1
            self.skipped_button.disabled = False
        if today.notices:
            show_message(texts.text("notice_title"), texts.notices_text(today.notices))

    def show_skipped(self) -> None:
        """Show which games gave no problems, and why."""
        if self.today is not None and self.today.skipped_games:
            show_message(texts.text("skipped_title"), texts.skipped_games_text(self.today.skipped_games))

    def start(self) -> None:
        """Open the quiz screen with today's problems (only after the games have been read)."""
        if self.today is None:
            return
        Window.unbind(on_key_down=self._on_key_down)
        self._on_start(self.today)

    def back(self) -> None:
        """Go back to the top screen (only after the games have been read)."""
        if self.today is None or self.back_button is None:
            return
        Window.unbind(on_key_down=self._on_key_down)
        self._on_back()

    def _on_key_down(self, _window, key: int, _scancode, _text, _modifiers) -> bool:
        """Start with Enter.

        The start is done a moment later, so that this Enter is not also taken
        by the quiz screen (as "next problem").
        """
        if key in KEY_ENTERS and self.today is not None:
            in_main_thread(self.start)()
            return True
        return False


def _today_text(today: TodayProblems) -> str:
    """Return the numbers of today's problems, the games that gave no problems, and the message of the day."""
    numbers = texts.text("splash_today", new=today.new_count, review=today.review_count)
    if today.session_limit is not None:
        numbers += "\n" + texts.text("splash_limit", left=today.session_limit)
    skipped = texts.skipped_text(today.skipped)
    if skipped:
        numbers += "\n\n" + skipped
    message = texts.notice_text(today.message)
    return f"{numbers}\n\n{message}" if message else numbers
