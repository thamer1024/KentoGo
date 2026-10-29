"""Small dialogs in KaTrain's colors: a message with an OK button, and a yes/no question.

The user is not expected to look at the console, so everything that the user
needs to know (for example that KataGo could not be started) is shown with
these dialogs. Kivy's labels cannot be selected, so the message is shown in a
text box that cannot be changed: the user can select it and copy it (Cmd+C).
The message is printed to the console too.

The keys work as the buttons do (see bind_dialog_keys): Return says OK or yes, and Esc says no,
cancels or closes. While a dialog is open, it takes these keys before the screen behind it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput

from kentogo.gui import texts, theme
from kentogo.gui.widgets import flat_button, wrapping_label

SPACING = 8  # dp
BUTTON_HEIGHT = 44  # dp
LONG_HEIGHT_RATIO = 0.96  # The height of a dialog with a long text, as a part of the window.
KEY_RETURNS = (13, 271)  # Return, and Enter of the number keys.
KEY_ESCAPE = 27


def bind_dialog_keys(
    dialog: ModalView, on_return: Callable[[], None] | None, on_escape: Callable[[], None] | None
) -> None:
    """Make Return and Esc work while a dialog is open. Call this before the dialog is opened.

    The keys are taken from the time the dialog has opened (so the key that opened it does not
    also close it) until it is closed. The dialog gets them before the screen behind it, and
    other keys go on as usual (for example, into a text box of the dialog).

    Args:
        dialog: The dialog.
        on_return: What Return does (OK, yes), or None if it does nothing in this dialog.
        on_escape: What Esc does (no, cancel, close), or None if it does nothing in this dialog.
    """

    def on_key_down(_window, key: int, *_args) -> bool:
        """Do what the key does in the dialog. True stops the key here."""
        if key in KEY_RETURNS and on_return is not None:
            on_return()
            return True
        if key == KEY_ESCAPE and on_escape is not None:
            on_escape()
            return True
        return False

    dialog.bind(
        on_open=lambda *_args: Window.bind(on_key_down=on_key_down),
        on_dismiss=lambda *_args: Window.unbind(on_key_down=on_key_down),
    )


def _popup(title: str, height: float) -> Popup:
    """Make an empty dialog that is closed only by its buttons."""
    return Popup(
        title=title,
        title_size=sp(18),
        size_hint=(0.6, None),
        height=dp(height),
        auto_dismiss=False,
        background="",
        background_color=theme.BACKGROUND_COLOR,
        separator_color=theme.BUTTON_COLOR,
    )


def show_message(title: str, message: str, on_close: Callable[[], None] | None = None) -> None:
    """Show a message that can be selected and copied, with an OK button. It is printed to the console too.

    Args:
        title: The title of the dialog.
        message: The message (plain text, not markup, because it can contain file names).
        on_close: Called when the dialog is closed, or None.
    """
    print(f"{title}: {message}", file=sys.stderr)
    _open_message(_popup(title, 360), message, on_close)


def show_long_message(title: str, message: str) -> None:
    """Show a long text (such as the AI review of a game) in a dialog almost as tall as the window.

    The text can be selected and copied, and it scrolls. It is not printed to the console.

    Args:
        title: The title of the dialog.
        message: The text (plain text, not markup).
    """
    popup = _popup(title, 0)
    popup.size_hint = (0.8, LONG_HEIGHT_RATIO)
    _open_message(popup, message, None)


def _open_message(popup: Popup, message: str, on_close: Callable[[], None] | None) -> None:
    """Put a text box with the message and an OK button into a dialog, and open it."""
    # A text box that cannot be changed, so that the text can be selected and copied. It scrolls by itself.
    box = TextInput(
        text=message,
        readonly=True,
        font_size=sp(15),
        background_normal="",
        background_active="",
        background_color=theme.BOX_BACKGROUND_COLOR,
        foreground_color=theme.TEXT_COLOR,
        cursor_color=(0, 0, 0, 0),
    )

    def close() -> None:
        """Close the dialog, then tell the caller."""
        popup.dismiss()
        if on_close is not None:
            on_close()

    content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
    content.add_widget(box)
    content.add_widget(flat_button(texts.text("ok"), close, size_hint_y=None, height=dp(BUTTON_HEIGHT)))
    popup.content = content
    bind_dialog_keys(popup, close, close)  # There is only OK, so Esc closes the dialog too.
    popup.open()


def confirm(
    question: str,
    on_yes: Callable[[], None],
    on_no: Callable[[], None],
    yes_label: str | None = None,
    no_label: str | None = None,
) -> None:
    """Ask a yes/no question in a small dialog, and call on_yes or on_no with the answer.

    Args:
        question: The question.
        on_yes: Called when the user says yes.
        on_no: Called when the user says no.
        yes_label: The text of the yes button (by default, "はい（保存する）").
        no_label: The text of the no button (by default, "いいえ").
    """
    popup = _popup(texts.text("reread_title"), 260)

    def answer(action: Callable[[], None]) -> None:
        """Close the dialog, then do what the answer asks."""
        popup.dismiss()
        action()

    content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
    content.add_widget(wrapping_label(text=question, valign="middle"))
    buttons = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(SPACING))
    buttons.add_widget(flat_button(yes_label or texts.text("yes_save"), lambda: answer(on_yes)))
    buttons.add_widget(flat_button(no_label or texts.text("no_cancel"), lambda: answer(on_no)))
    content.add_widget(buttons)
    popup.content = content
    bind_dialog_keys(popup, lambda: answer(on_yes), lambda: answer(on_no))
    popup.open()


def choose(title: str, question: str, choices: list[tuple[str, Callable[[], None]]]) -> None:
    """Ask the user to choose one of some buttons in a dialog, and call the action of the chosen one.

    Args:
        title: The title of the dialog.
        question: The question.
        choices: (label, action) of each button, in order from the left. None of them is OK or
            cancel, so Return and Esc do nothing in this dialog.
    """
    popup = _popup(title, 240)

    def answer(action: Callable[[], None]) -> None:
        """Close the dialog, then do what the chosen button asks."""
        popup.dismiss()
        action()

    content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
    content.add_widget(wrapping_label(text=question, halign="center", valign="middle"))
    buttons = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(SPACING))
    for label, action in choices:
        buttons.add_widget(flat_button(label, lambda action=action: answer(action)))
    content.add_widget(buttons)
    popup.content = content
    popup.open()
