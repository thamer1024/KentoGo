"""A row that shows the name of the SGF file of a screen, so that it can be copied.

The name is in a box that can be selected, and the button next to it copies the whole name.
"""

from __future__ import annotations

from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput

from kentogo.gui import texts, theme
from kentogo.gui.widgets import flat_button

ROW_HEIGHT = 32  # dp


class FileNameRow(BoxLayout):
    """The name of an SGF file, in a box that can be selected, and a button that copies it."""

    def __init__(self, **kwargs):
        """Make the row, with no name yet.

        Args:
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(8), **kwargs)
        self.name_box = TextInput(
            readonly=True,
            multiline=False,
            font_size=sp(13),
            background_normal="",
            background_active="",
            background_color=theme.BACKGROUND_COLOR,
            foreground_color=theme.TEXT_COLOR,
            cursor_color=theme.TEXT_COLOR,
        )
        self.add_widget(self.name_box)
        self.add_widget(flat_button(texts.lazy("copy_file_name"), self.copy, size_hint_x=None, width=dp(72)))

    def set_name(self, name: str) -> None:
        """Show the name of a file ("" shows nothing)."""
        self.name_box.text = name

    def copy(self) -> None:
        """Copy the name to the clipboard (nothing if there is no name)."""
        if self.name_box.text:
            Clipboard.copy(self.name_box.text)
