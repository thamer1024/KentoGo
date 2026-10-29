"""Small helpers that make widgets in KaTrain's colors, used by several screens.

Texts that are shown with set_text are made again when the language is changed
(see relabel_all), so the screens change their language at once, as in KaTrain.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from kentogo.gui import theme

# The widgets whose texts are made by set_text. Each widget keeps its own functions (in
# TEXT_MAKERS_ATTRIBUTE), so that a function that refers to the widget does not keep it alive.
_LOCALIZED: weakref.WeakSet = weakref.WeakSet()
TEXT_MAKERS_ATTRIBUTE = "kentogo_text_makers"


def set_text(widget, make: Callable[[], str], attribute: str = "text") -> None:
    """Show a text on a widget, and show it again in the new language when the language is changed.

    Args:
        widget: A Kivy widget, such as a Label or a Button.
        make: Makes the text in the language used now (for example texts.lazy("back")).
        attribute: The property that shows the text.
    """
    makers = getattr(widget, TEXT_MAKERS_ATTRIBUTE, None)
    if makers is None:
        makers = {}
        setattr(widget, TEXT_MAKERS_ATTRIBUTE, makers)
        _LOCALIZED.add(widget)
    makers[attribute] = make
    setattr(widget, attribute, make())


def relabel_all() -> None:
    """Make the texts of all widgets shown with set_text again, in the language used now."""
    for widget in list(_LOCALIZED):
        for attribute, make in getattr(widget, TEXT_MAKERS_ATTRIBUTE).items():
            setattr(widget, attribute, make())


def set_background(widget, color: tuple) -> None:
    """Fill the area of a widget with a color, behind its children."""
    with widget.canvas.before:
        Color(*color)
        rectangle = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(
        pos=lambda _, pos: setattr(rectangle, "pos", pos), size=lambda _, size: setattr(rectangle, "size", size)
    )


def flat_button(label: str | Callable[[], str], action: Callable[[], None], **kwargs) -> Button:
    """Make a flat button in KaTrain's colors that calls action when it is released.

    A disabled button is drawn darker, and its text is dimmed by Kivy, so that it
    looks like it cannot be pressed.

    Args:
        label: The text of the button, or a function that makes it (then the text
            follows the language, see set_text).
        action: Called when the button is released.
        **kwargs: Other arguments of Kivy's Button.
    """
    button = Button(
        background_normal="",
        background_disabled_normal="",
        background_color=theme.BUTTON_COLOR,
        **kwargs,
    )
    if callable(label):
        set_text(button, label)
    else:
        button.text = label
    button.bind(on_release=lambda *_: action())
    button.bind(
        disabled=lambda widget, disabled: setattr(
            widget, "background_color", theme.BUTTON_DISABLED_COLOR if disabled else theme.BUTTON_COLOR
        )
    )
    return button


def wrapping_label(halign: str = "left", valign: str = "top", **kwargs) -> Label:
    """Make a label whose text uses markup and wraps at the width of the label.

    Args:
        halign: How to place the lines: "left", "center" or "right".
        valign: Where to place the text: "top", "middle" or "bottom".
        **kwargs: Other arguments of Kivy's Label.
    """
    label = Label(markup=True, halign=halign, valign=valign, color=theme.TEXT_COLOR, **kwargs)
    label.bind(size=lambda widget, size: setattr(widget, "text_size", size))
    return label


def fitting_label(min_height: float, halign: str = "left", **kwargs) -> Label:
    """Make a label whose text uses markup, wraps at its width, and grows taller when the text needs it.

    In a narrow window the lines wrap more, so the label grows and no text is cut off.
    It is never lower than min_height, so that the screen does not jump while the text changes.

    Args:
        min_height: The lowest height of the label, in pixels.
        halign: How to place the lines: "left", "center" or "right".
        **kwargs: Other arguments of Kivy's Label.
    """
    label = Label(markup=True, halign=halign, valign="top", color=theme.TEXT_COLOR, size_hint_y=None, **kwargs)
    label.height = min_height
    label.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
    label.bind(texture_size=lambda widget, size: setattr(widget, "height", max(min_height, size[1])))
    return label


def growing_label() -> Label:
    """Make a label for long text in a scroll view: it wraps and grows as tall as its text.

    Markup is off, because the notes are written by the user and can contain "[" and "]".
    """
    label = Label(markup=False, halign="left", valign="top", size_hint_y=None, color=theme.TEXT_COLOR)
    label.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
    label.bind(texture_size=lambda widget, size: setattr(widget, "height", size[1]))
    return label


def in_main_thread(function: Callable) -> Callable:
    """Wrap a function so that, when it is called from any thread, it runs later in Kivy's main thread.

    KataGo's answers and the games read at the start come in background threads,
    but widgets can only be changed in the main thread.
    """
    return lambda *args: Clock.schedule_once(lambda _dt: function(*args))


def text_box(readonly: bool) -> TextInput:
    """Make a box for a long text, such as a prompt, or an answer to paste or that arrives from an AI."""
    return TextInput(
        readonly=readonly,
        font_size=sp(13),
        background_normal="",
        background_active="",
        background_color=theme.BACKGROUND_COLOR,
        foreground_color=theme.TEXT_COLOR,
        cursor_color=theme.TEXT_COLOR,
    )


def title_label(make: Callable[[], str]) -> Label:
    """Make the title line above a text box (make gives its text, see set_text)."""
    label = fitting_label(dp(24))
    set_text(label, make)
    return label
