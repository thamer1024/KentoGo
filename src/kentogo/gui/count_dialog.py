"""The dialog in which the user enters the territory that the user counted (整地終了).

The user enters the territory of black and of white, without komi. "判定する" passes them on
(a box that is not a whole number is told, and the dialog stays open); "キャンセル" closes it.
"""

from __future__ import annotations

from collections.abc import Callable

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput

from kentogo.gui import texts, theme
from kentogo.gui.widgets import fitting_label, flat_button, set_text
from kentogo.seichi.territory import TerritoryCount

SPACING = 8  # dp
ROW_HEIGHT = 44  # dp


def ask_territory(on_entered: Callable[[TerritoryCount], None]) -> None:
    """Open the dialog, and call on_entered with the territory that the user entered."""
    popup = Popup(
        title=texts.text("count_title"),
        title_size=sp(18),
        size_hint=(0.5, None),
        height=dp(300),
        auto_dismiss=False,
        background="",
        background_color=theme.BACKGROUND_COLOR,
        separator_color=theme.BUTTON_COLOR,
    )
    content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
    boxes = {color: _number_row(content, f"count_{color}") for color in ("black", "white")}
    message = fitting_label(dp(24))
    content.add_widget(message)

    def enter() -> None:
        """Pass on the numbers, or tell that they are not whole numbers."""
        try:
            entered = TerritoryCount(int(boxes["black"].text), int(boxes["white"].text))
        except ValueError:
            set_text(message, texts.lazy("count_need_numbers"))
            return
        popup.dismiss()
        on_entered(entered)

    buttons = BoxLayout(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(SPACING))
    buttons.add_widget(flat_button(texts.text("count_judge"), enter))
    buttons.add_widget(flat_button(texts.text("cancel"), popup.dismiss))
    content.add_widget(buttons)
    popup.content = content
    popup.open()


def _number_row(content: BoxLayout, label_key: str) -> TextInput:
    """Add a row with a label and a box for a whole number, and return the box."""
    row = BoxLayout(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(SPACING))
    label = fitting_label(dp(ROW_HEIGHT))
    set_text(label, texts.lazy(label_key))
    row.add_widget(label)
    box = TextInput(
        multiline=False,
        input_filter="int",
        font_size=sp(18),
        size_hint_x=0.4,
        background_normal="",
        background_active="",
        background_color=theme.BACKGROUND_COLOR,
        foreground_color=theme.TEXT_COLOR,
        cursor_color=theme.TEXT_COLOR,
    )
    row.add_widget(box)
    content.add_widget(row)
    return box
