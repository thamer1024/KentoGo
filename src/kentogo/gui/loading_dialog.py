"""The dialog shown while KataGo loads at the start of the app (as KaTrain waits for its engine).

It tells which model is loaded ("loading_main", then "loading_compare"), and how long it may
still take: the time that the same KataGo took last time, minus the time that has passed, with
a bar (see katago.startup). A KataGo that has not been started before shows only the time that
has passed. It closes by itself when every KataGo is ready, or has failed (the reason is then
shown by the notices). The user can also close it and go on: KataGo goes on loading, and a
question asked before it is ready waits for it.
"""

from __future__ import annotations

from collections.abc import Callable

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar

from kentogo.gui import texts, theme
from kentogo.gui.dialogs import BUTTON_HEIGHT, SPACING, bind_dialog_keys
from kentogo.gui.widgets import flat_button, wrapping_label
from kentogo.katago.startup import Loading, LoadingState

UPDATE_SECONDS = 0.5  # How often the dialog looks at KataGo.
DIALOG_HEIGHT = 230  # dp


class LoadingDialog:
    """A dialog that follows the loading of KataGo until it is done."""

    def __init__(self, loading: Loading, on_done: Callable[[], None]):
        """Prepare the dialog.

        Args:
            loading: The stages of the loading.
            on_done: Called once when every KataGo is ready or has failed (also when the dialog was closed before).
        """
        self.loading = loading
        self.on_done = on_done
        self.popup: Popup | None = None
        self.message = wrapping_label(halign="center", valign="middle", font_size=sp(16))
        self.bar = ProgressBar(max=1.0, size_hint_y=None, height=dp(16))
        self._event = None

    def open(self) -> None:
        """Open the dialog, unless KataGo is ready already (then on_done is called at once)."""
        state = self.loading.update()
        if state is None:
            self.on_done()
            return
        self.popup = self._make_popup()
        self._show(state)
        self.popup.open()
        self._event = Clock.schedule_interval(lambda _dt: self._update(), UPDATE_SECONDS)

    def _make_popup(self) -> Popup:
        """Make the dialog: the message, the bar and a button to go on without waiting."""
        popup = Popup(
            title=texts.text("loading_title"),
            title_size=sp(18),
            size_hint=(0.6, None),
            height=dp(DIALOG_HEIGHT),
            auto_dismiss=False,
            background="",
            background_color=theme.BACKGROUND_COLOR,
            separator_color=theme.BUTTON_COLOR,
        )
        content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
        content.add_widget(self.message)
        content.add_widget(self.bar)
        hide = flat_button(texts.text("loading_hide"), self._hide, size_hint_y=None, height=dp(BUTTON_HEIGHT))
        content.add_widget(hide)
        popup.content = content
        bind_dialog_keys(popup, None, self._hide)
        return popup

    def _update(self) -> None:
        """Show the state now; when the loading is done, close the dialog and tell the caller."""
        state = self.loading.update()
        if state is not None:
            self._show(state)
            return
        self._event.cancel()
        self._hide()
        self.on_done()

    def _show(self, state: LoadingState) -> None:
        """Show what is loaded, and the time left (or passed)."""
        remaining = state.remaining
        if remaining is None:
            time_text = texts.text("loading_elapsed", seconds=round(state.elapsed))
        else:
            time_text = texts.text("loading_remaining", seconds=max(1, round(remaining)))
        self.message.text = f"{texts.text(state.text_key)}\n{time_text}"
        self.bar.opacity = 0 if remaining is None else 1
        self.bar.value = 0 if remaining is None else state.elapsed / state.expected

    def _hide(self) -> None:
        """Close the dialog; the loading is still followed, and on_done is still called when it is done."""
        if self.popup is not None:
            self.popup.dismiss()
            self.popup = None
