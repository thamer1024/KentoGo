"""The menu of the AI commentary: which way to give games to an AI.

- The API mode for the new games (gui.batch_screen): the games changed since the last run.
- The API mode for one game (gui.api_screen).
- The paste mode (gui.paste_screen): the prompt is pasted into the chat screen of any AI.
"""

from __future__ import annotations

from collections.abc import Callable

from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout

from kentogo.gui import texts, theme
from kentogo.gui.widgets import flat_button, set_background, set_text, wrapping_label

BUTTON_HEIGHT = 52  # dp


class CommentaryMenu(AnchorLayout):
    """The menu of the AI commentary."""

    def __init__(self, choices: list[tuple[str, Callable[[], None]]], on_back: Callable[[], None], **kwargs):
        """Make the menu.

        Args:
            choices: For each button, the key of its text (see gui.texts) and what it does, from the top.
            on_back: Called by the back button.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(anchor_x="center", anchor_y="center", **kwargs)
        height = 56 + (len(choices) + 1) * (BUTTON_HEIGHT + 12) + 48
        box = BoxLayout(orientation="vertical", size_hint=(None, None), size=(dp(560), dp(height)), padding=dp(24))
        box.spacing = dp(12)
        set_background(box, theme.BOX_BACKGROUND_COLOR)
        title = wrapping_label(halign="center", valign="middle", font_size=sp(26), size_hint_y=None, height=dp(56))
        set_text(title, texts.lazy("commentary_title"))
        box.add_widget(title)
        for key, action in choices:
            box.add_widget(flat_button(texts.lazy(key), action, size_hint_y=None, height=dp(BUTTON_HEIGHT)))
        box.add_widget(flat_button(texts.lazy("back_to_top"), on_back, size_hint_y=None, height=dp(BUTTON_HEIGHT)))
        self.add_widget(box)
