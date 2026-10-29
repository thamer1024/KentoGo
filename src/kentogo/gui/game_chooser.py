"""A wide dialog that lists the games of the games folder, to choose one to look at.

The games are listed the newest first, one line each with the whole file name (a name that
is still too long is cut with "…", never wrapped onto the next line). A check box shows only
the games with an AI commentary. The list is read in a background thread (see record.library).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from kentogo.gui import texts, theme, viewer_model
from kentogo.gui.check_box import MaterialCheckBox
from kentogo.gui.dialogs import bind_dialog_keys
from kentogo.gui.widgets import fitting_label, flat_button, in_main_thread, set_text
from kentogo.record.library import GameFile, games_with_ai, list_games

ROW_HEIGHT = 40  # dp


class GameChooser(Popup):
    """The dialog that lists the games."""

    def __init__(self, folder: Path, on_chosen: Callable[[Path], None], **kwargs):
        """Make the dialog, and start reading the list. Call open() to show it.

        Args:
            folder: The games folder.
            on_chosen: Called with the SGF file that the user chose (the dialog is closed first).
            **kwargs: Kivy's Popup arguments.
        """
        super().__init__(
            title=texts.text("viewer_choose"),
            title_size=sp(18),
            size_hint=(0.85, 0.9),
            auto_dismiss=False,
            background="",
            background_color=theme.BACKGROUND_COLOR,
            separator_color=theme.BUTTON_COLOR,
            **kwargs,
        )
        self._on_chosen = on_chosen
        self._games: list[GameFile] = []
        self.content = self._content()
        bind_dialog_keys(self, None, self.dismiss)  # Esc closes the list; a game is chosen with its button.
        threading.Thread(target=lambda: self._load(folder), daemon=True).start()

    def _content(self) -> BoxLayout:
        """Make the check box, the list and the close button."""
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(4))
        row = BoxLayout(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(8))
        self.only_ai = MaterialCheckBox(size_hint=(None, None), size=(dp(ROW_HEIGHT), dp(ROW_HEIGHT)))
        self.only_ai.bind(active=lambda *_: self._fill())
        label = fitting_label(dp(ROW_HEIGHT))
        set_text(label, texts.lazy("viewer_only_ai"))
        row.add_widget(self.only_ai)
        row.add_widget(label)
        self.status = fitting_label(dp(28))
        set_text(self.status, texts.lazy("viewer_loading_list"))
        self.game_list = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
        self.game_list.bind(minimum_height=self.game_list.setter("height"))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.game_list)
        close = flat_button(texts.lazy("close"), self.dismiss, size_hint_y=None, height=dp(44))
        for widget in (row, self.status, scroll, close):
            box.add_widget(widget)
        return box

    def _load(self, folder: Path) -> None:
        """Read the list of games (in a background thread) and show it."""
        games = list_games(folder)
        in_main_thread(self._set_games)(games)

    def _set_games(self, games: list[GameFile]) -> None:
        """Keep the list of games and show it."""
        self._games = games
        self._fill()

    def _fill(self) -> None:
        """Show the games, only those with an AI commentary when the check box is on."""
        self.game_list.clear_widgets()
        games = games_with_ai(self._games) if self.only_ai.active else self._games
        set_text(self.status, str if games else texts.lazy("viewer_no_games"))
        for game in games:
            self.game_list.add_widget(self._row(game))

    def _row(self, game: GameFile):
        """Make the button of one game: one line, cut with "…" if the name is too long."""
        button = flat_button(viewer_model.game_label(game), lambda: self._choose(game.path))
        button.size_hint_y = None
        button.height = dp(ROW_HEIGHT)
        button.halign = "left"
        button.valign = "middle"
        button.shorten = True
        button.shorten_from = "right"
        button.bind(size=lambda widget, size: setattr(widget, "text_size", (size[0] - dp(16), size[1])))
        return button

    def _choose(self, path: Path) -> None:
        """Close the dialog and give the chosen game."""
        self.dismiss()
        self._on_chosen(path)
