"""The top screen: the first screen at every start, from which each practice and tool is chosen.

It shows a button for each choice (the quiz, and the territory counting practice when it is
turned on in the settings; later also looking through games and the AI commentary), the ☰
menu with the settings screens, the flags of the languages, and at the bottom the version of
KentoGo (only in the programs of the releases). Every other screen has a button to come back
here.
"""

from __future__ import annotations

from collections.abc import Callable

from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from kentogo.gui import texts, theme
from kentogo.gui.menu import flag_row, menu_row
from kentogo.gui.settings_form import PAGES
from kentogo.gui.widgets import flat_button, set_background, set_text, wrapping_label

BUTTON_HEIGHT = 52  # dp


class TopScreen(BoxLayout):
    """The top screen."""

    def __init__(
        self,
        choices: list[tuple[str, Callable[[], None]]],
        open_settings: Callable[[str], None],
        version: str = "",
        **kwargs,
    ):
        """Make the screen.

        Args:
            choices: For each button, the key of its text (see gui.texts) and what it does, from the top.
            open_settings: Opens a settings screen (one of settings_form.PAGES).
            version: The version of KentoGo (see kentogo.version); nothing is shown when it is "".
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="vertical", **kwargs)
        self.add_widget(menu_row(open_settings, PAGES))
        center = AnchorLayout(anchor_x="center", anchor_y="center")
        center.add_widget(_box(choices))
        self.add_widget(center)
        if version:
            self.add_widget(_version_label(version))


def _box(choices: list[tuple[str, Callable[[], None]]]) -> BoxLayout:
    """Make the box in the middle: the title, the buttons, and the flags."""
    height = 64 + 28 + len(choices) * (BUTTON_HEIGHT + 12) + 48 + 80
    box = BoxLayout(orientation="vertical", size_hint=(None, None), size=(dp(520), dp(height)), padding=dp(24))
    box.spacing = dp(12)
    set_background(box, theme.BOX_BACKGROUND_COLOR)
    title = wrapping_label(halign="center", valign="middle", font_size=sp(40), size_hint_y=None, height=dp(64))
    set_text(title, texts.lazy("splash_title"))
    subtitle = wrapping_label(halign="center", size_hint_y=None, height=dp(28))
    set_text(subtitle, texts.lazy("splash_subtitle"))
    box.add_widget(title)
    box.add_widget(subtitle)
    for key, action in choices:
        box.add_widget(flat_button(texts.lazy(key), action, size_hint_y=None, height=dp(BUTTON_HEIGHT)))
    box.add_widget(flag_row())
    return box


def _version_label(version: str) -> Label:
    """Make the small line at the bottom with the version of KentoGo."""
    return Label(
        text=f"KentoGo {version}",
        font_size=sp(13),
        color=theme.VERSION_TEXT_COLOR,
        size_hint_y=None,
        height=dp(28),
    )
