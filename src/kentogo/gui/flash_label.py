"""A short text shown over the board for a moment, such as the name of the sequence chosen with Tab.

The text is shown at once, stays for SHOWN_SECONDS, so that it can be read, and then fades out in
FADE_SECONDS. A new text replaces the one shown.
"""

from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.label import Label

from kentogo.gui.widgets import set_background

SHOWN_SECONDS = 0.6  # How long the text is shown before it fades out.
FADE_SECONDS = 0.3  # How long it fades out.
FONT_SIZE = 28  # sp.
BACKGROUND_COLOR = (0, 0, 0, 0.72)  # Dark, so that the text can be read on the board and the stones.
PADDING = (32, 16)  # dp, around the text (width, height).


class FlashLabel(Label):
    """A text in big letters on a dark box, shown for a moment (see flash). It is hidden at first."""

    def __init__(self, **kwargs):
        """Make the label, hidden."""
        super().__init__(font_size=sp(FONT_SIZE), bold=True, opacity=0, size_hint=(None, None), **kwargs)
        set_background(self, BACKGROUND_COLOR)
        self.bind(texture_size=self._fit)
        self._fade_event = None

    def _fit(self, *_args) -> None:
        """Make the box as big as the text with some space around it."""
        width, height = self.texture_size
        self.size = (width + dp(PADDING[0]), height + dp(PADDING[1]))

    def flash(self, text: str) -> None:
        """Show a text at once, and fade it out after SHOWN_SECONDS."""
        Animation.cancel_all(self, "opacity")
        if self._fade_event is not None:
            self._fade_event.cancel()
        self.text = text
        self.opacity = 1
        self._fade_event = Clock.schedule_once(self._fade_out, SHOWN_SECONDS)

    def _fade_out(self, _seconds: float) -> None:
        """Fade the text out."""
        self._fade_event = None
        Animation(opacity=0, duration=FADE_SECONDS).start(self)
