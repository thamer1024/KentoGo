"""The menu button: KaTrain's "hamburger" button, which opens a list of the settings screens and the flags.

KaTrain opens its settings screens ("General & Engine settings", and so on)
from a menu behind this button. KentoGo does the same, with a small list that
opens under the button (only the top screen has it). Under the pages is a row
with the flags of the languages, as in KaTrain's menu: a flag shows all screens
in its language at once (see KentoGoApp.change_language).
"""

from __future__ import annotations

from collections.abc import Callable

from kivy.app import App
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.image import Image
from kivy.uix.widget import Widget

from kentogo.gui import texts, theme
from kentogo.gui.widgets import flat_button, set_background

ICON_SIZE = 32  # dp
ITEM_HEIGHT = 44  # dp
FLAG_SIZE = 28  # dp
FLAG_SPACING = 4  # dp
MENU_WIDTH = len(texts.LANGUAGES) * (FLAG_SIZE + FLAG_SPACING) + 8  # dp. As wide as the row of flags.


class IconButton(ButtonBehavior, Image):
    """A button that shows only an image."""


def menu_row(open_page: Callable[[str], None], pages: tuple[str, ...]) -> BoxLayout:
    """Make the row with the menu button at the left.

    Args:
        open_page: Opens a settings screen. It is given one of the pages.
        pages: The settings screens in the menu (settings_form.PAGES).

    Returns:
        The row, to put at the top of the panel.
    """
    row = BoxLayout(size_hint_y=None, height=dp(ICON_SIZE + 4))
    button = IconButton(source=str(theme.MENU_IMAGE), size_hint=(None, None), size=(dp(ICON_SIZE), dp(ICON_SIZE)))
    button.bind(on_release=lambda widget: _open_menu(widget, open_page, pages))
    row.add_widget(button)
    row.add_widget(Widget())  # Keeps the button at the left.
    return row


def _open_menu(button: Widget, open_page: Callable[[str], None], pages: tuple[str, ...]) -> None:
    """Open the list of settings screens, with the flags of the languages, under the button."""
    menu = DropDown(auto_width=False, width=dp(MENU_WIDTH))

    def choose(page: str) -> None:
        """Close the list, then open the chosen screen."""
        menu.dismiss()
        open_page(page)

    # The list must stand out from the panel under it: a dark frame with a light border,
    # and lighter items (the color of buttons).
    menu.container.padding = dp(4)
    menu.container.spacing = dp(4)
    set_background(menu.container, theme.BACKGROUND_COLOR)
    _set_border(menu.container, theme.MENU_BORDER_COLOR)
    for page in pages:
        item = flat_button(texts.text(f"page_{page}"), lambda page=page: choose(page), size_hint_y=None)
        item.height = dp(ITEM_HEIGHT)
        menu.add_widget(item)
    menu.add_widget(flag_row(on_chosen=menu.dismiss))
    menu.open(button)


def flag_row(on_chosen: Callable[[], None] | None = None) -> BoxLayout:
    """Make a row with the flags of all languages. A flag shows the screens in its language.

    Args:
        on_chosen: Called first when a flag is pressed (for example, to close the menu).
    """
    row = BoxLayout(size_hint_y=None, height=dp(FLAG_SIZE + 8), spacing=dp(FLAG_SPACING))
    row.add_widget(Widget())  # Keeps the flags in the middle.
    for language in texts.LANGUAGES:
        flag = IconButton(
            source=str(theme.flag_image(language)), size_hint=(None, None), size=(dp(FLAG_SIZE), dp(FLAG_SIZE))
        )
        flag.pos_hint = {"center_y": 0.5}
        flag.bind(on_release=lambda _widget, language=language: _choose_language(language, on_chosen))
        row.add_widget(flag)
    row.add_widget(Widget())
    return row


def _choose_language(language: str, on_chosen: Callable[[], None] | None) -> None:
    """Show all screens in a language (the app also keeps it for the next start)."""
    if on_chosen is not None:
        on_chosen()
    App.get_running_app().change_language(language)


def _set_border(widget: Widget, color: tuple) -> None:
    """Draw a thin line around a widget, in front of it."""
    with widget.canvas.after:
        Color(*color)
        line = Line(width=dp(1))

    def place(*_args) -> None:
        """Keep the line on the edge of the widget."""
        line.rectangle = (widget.x, widget.y, widget.width, widget.height)

    widget.bind(pos=place, size=place)
