"""A row of inputs for one game of the AI commentary: the user's color, rank, and the opponent's rank.

The values are chosen from lists (see gui.commentary_texts). The labels of the lists are made
in the language used when the row is made.
"""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.spinner import Spinner

from kentogo.commentary.candidates import GameCandidate
from kentogo.commentary.job import GameRequest
from kentogo.gui import commentary_texts, texts, theme
from kentogo.gui.widgets import fitting_label, set_text

ROW_HEIGHT = 40  # dp


class GameInputs(BoxLayout):
    """The inputs of one game."""

    def __init__(self, **kwargs):
        """Make the row, with every value "not given"."""
        super().__init__(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(8), **kwargs)
        self._color = self._choice("commentary_my_color", commentary_texts.COLORS, commentary_texts.color_label)
        self._rank = self._choice("commentary_my_rank", commentary_texts.RANK_CHOICES, commentary_texts.rank_label)
        self._relation = self._choice(
            "commentary_relation", commentary_texts.RELATION_CHOICES, commentary_texts.relation_label
        )

    def set_values(self, color: str, rank: str, relation: str) -> None:
        """Show the values of a game ("" for not given)."""
        for spinner, values, label, value in (
            (self._color, commentary_texts.COLORS, commentary_texts.color_label, color),
            (self._rank, commentary_texts.RANK_CHOICES, commentary_texts.rank_label, rank),
            (self._relation, commentary_texts.RELATION_CHOICES, commentary_texts.relation_label, relation),
        ):
            spinner.text = label(value if value in values else "")

    def values(self) -> tuple[str, str, str]:
        """Return the chosen (color, rank, relation), each "" if not given."""
        return (
            _value(self._color, commentary_texts.COLORS, commentary_texts.color_label),
            _value(self._rank, commentary_texts.RANK_CHOICES, commentary_texts.rank_label),
            _value(self._relation, commentary_texts.RELATION_CHOICES, commentary_texts.relation_label),
        )

    def _choice(self, title_key: str, values: tuple[str, ...], label) -> Spinner:
        """Add a title and a list of choices to the row, and return the list."""
        title = fitting_label(dp(ROW_HEIGHT), halign="right", size_hint_x=0.6)
        set_text(title, texts.lazy(title_key))
        spinner = Spinner(text=label(""), values=[label(value) for value in values], background_normal="")
        spinner.background_color = theme.BUTTON_COLOR
        self.add_widget(title)
        self.add_widget(spinner)
        return spinner


def request_for(candidate: GameCandidate, inputs: GameInputs) -> GameRequest | None:
    """Return the request of a game with the chosen inputs, or None if the user's color is not chosen."""
    color, rank, relation = inputs.values()
    return GameRequest(candidate.path, color, rank, relation) if color else None


def _value(spinner: Spinner, values: tuple[str, ...], label) -> str:
    """Return the value whose label is shown in a list ("" if none matches)."""
    return next((value for value in values if label(value) == spinner.text), "")
