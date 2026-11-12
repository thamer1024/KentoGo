"""The list of the games to analyze, opened by the top screen's "KataGoで棋譜解析" (see gui.analysis_start).

Each game of the analysis's folder is one row: a check box, the file name, and what the game is
(not analyzed, analyzed by KaTrain, analyzed by KentoGo, or a file that cannot be read). The games
analyzed by KentoGo are listed only when "KentoGoで解析済みの棋譜も表示する" is on. At first only the
games not analyzed yet are checked (see analysis_run.FolderGame.checked_first); "すべて選ぶ" and
"すべて外す" check or uncheck all the games that are listed. The start button tells how many games
are chosen, and gives them to the run (see analysis_run.GameChoice).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import escape_markup

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis_run import FolderGame, FolderGames, GameChoice
from kentogo.gui import texts, theme
from kentogo.gui.check_box import MaterialCheckBox
from kentogo.gui.widgets import fitting_label, flat_button, set_background, wrapping_label

SPACING = 8  # dp
BUTTON_HEIGHT = 44  # dp
ROW_HEIGHT = 36  # dp. One game of the list.
CHECK_SIZE = 32  # dp


class GameRow(BoxLayout):
    """One game of the list: the check box, the file name and what the game is."""

    def __init__(self, game: FolderGame, checked: bool, on_check: Callable[[FolderGame, bool], None], **kwargs):
        """Make the row; on_check is called with the game and its new check."""
        super().__init__(size_hint_y=None, height=dp(ROW_HEIGHT), spacing=dp(SPACING), **kwargs)
        set_background(self, theme.BACKGROUND_COLOR)
        self.check = MaterialCheckBox(size_hint=(None, None), size=(dp(CHECK_SIZE), dp(CHECK_SIZE)), active=checked)
        self.check.bind(active=lambda _box, active: on_check(game, active))
        name = wrapping_label(valign="middle", text=escape_markup(game.path.name))
        state = wrapping_label(valign="middle", size_hint_x=0.3, text=texts.analysis_state_text(game.state))
        for widget in (self.check, name, state):
            self.add_widget(widget)


class AnalysisChooser(Popup):
    """The dialog that lists the games of the analysis's folder, to choose the ones to analyze."""

    def __init__(
        self, games: FolderGames, analysis: AnalysisSettings, on_start: Callable[[list[Path]], None], **kwargs
    ):
        """Make the dialog and list the games.

        Args:
            games: The games of the folder (see analysis_run.list_games).
            analysis: The settings of the analysis (which games are checked at first).
            on_start: Called with the chosen games when the start button is pressed (the dialog is closed first).
            **kwargs: Kivy's popup arguments.
        """
        super().__init__(
            title=texts.text("analysis_choose_title"),
            title_size=sp(18),
            size_hint=(0.8, 0.85),
            auto_dismiss=False,
            background="",
            background_color=theme.BACKGROUND_COLOR,
            separator_color=theme.BUTTON_COLOR,
            **kwargs,
        )
        self.choice = GameChoice(games, analysis)
        self._on_start = on_start
        self.rows: list[GameRow] = []
        self.list_box = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.start_button = flat_button("", self.start)
        content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
        intro = fitting_label(dp(60))
        intro.text = texts.text("analysis_choose_intro", folder=games.folder, backup=games.backup)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.list_box)
        for widget in (intro, self._list_options(games), scroll, self._buttons()):
            content.add_widget(widget)
        self.content = content
        self._fill()

    def _list_options(self, games: FolderGames) -> BoxLayout:
        """Make the row above the list: show the games analyzed by KentoGo, check all, uncheck all."""
        row = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(SPACING))
        show = MaterialCheckBox(size_hint=(None, None), size=(dp(CHECK_SIZE), dp(CHECK_SIZE)))
        show.bind(active=lambda _box, active: self.show_kentogo(active))
        label = wrapping_label(valign="middle", text=texts.text("analysis_show_kentogo", count=games.kentogo_count))
        row.add_widget(show)
        row.add_widget(label)
        row.add_widget(flat_button(texts.text("analysis_select_all"), self.check_all, size_hint_x=0.2))
        row.add_widget(flat_button(texts.text("analysis_select_none"), self.check_none, size_hint_x=0.2))
        return row

    def _buttons(self) -> BoxLayout:
        """Make the buttons at the bottom: start, and close."""
        buttons = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(SPACING))
        buttons.add_widget(self.start_button)
        buttons.add_widget(flat_button(texts.text("close"), self.dismiss, size_hint_x=0.3))
        return buttons

    def _fill(self) -> None:
        """List the games that are listed now, with their checks."""
        self.list_box.clear_widgets()
        choice = self.choice
        self.rows = [GameRow(game, choice.is_checked(game), self._check) for game in choice.listed()]
        for row in self.rows:
            self.list_box.add_widget(row)
        if not self.rows:
            empty = fitting_label(dp(60))
            empty.text = texts.text("analysis_choose_empty")
            self.list_box.add_widget(empty)
        self._show_count()

    def _check(self, game: FolderGame, checked: bool) -> None:
        """Keep the new check of a game, and show the number of chosen games."""
        self.choice.set_checked(game, checked)
        self._show_count()

    def _show_count(self) -> None:
        """Show the number of chosen games on the start button, which cannot be pressed without any."""
        count = len(self.choice.chosen())
        self.start_button.text = texts.text("analysis_run_chosen", count=count)
        self.start_button.disabled = count == 0

    def show_kentogo(self, shown: bool) -> None:
        """List the games analyzed by KentoGo too, or hide them again."""
        self.choice.with_kentogo = shown
        self._fill()

    def check_all(self) -> None:
        """Check all the games that are listed."""
        self.choice.set_all_listed(True)
        self._fill()

    def check_none(self) -> None:
        """Uncheck all the games that are listed."""
        self.choice.set_all_listed(False)
        self._fill()

    def start(self) -> None:
        """Close the dialog and give the chosen games to the run."""
        chosen = self.choice.chosen()
        self.dismiss()
        self._on_start(chosen)
