"""The analysis of the games with KataGo, started from the top screen ("KataGoで棋譜解析").

The games of the analysis's folder are read in a background thread (reading many games can take
long), while a small dialog tells that they are counted. Then the list of the games is shown to
choose the ones to analyze (see gui.analysis_chooser), and the chosen games are analyzed with the
progress shown (see gui.analysis_popup). When the folder has no game to analyze, only the reason is
told. The settings saved last are used; they are changed on the settings screen ("KataGo棋譜解析").
"""

from __future__ import annotations

import threading
from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.popup import Popup

from kentogo.analysis_run import AnalysisListener, AnalysisSummary, FolderGames
from kentogo.app_settings import AppSettings
from kentogo.gui import texts, theme
from kentogo.gui.analysis_chooser import AnalysisChooser
from kentogo.gui.analysis_popup import AnalysisPopup, FolderAnalysis
from kentogo.gui.dialogs import show_message
from kentogo.gui.widgets import fitting_label, in_main_thread


def start_folder_analysis(settings: AppSettings, analysis: FolderAnalysis) -> None:
    """Count the games of the analysis's folder, then let the user choose the games to analyze."""
    counting = _counting_dialog()
    counting.open()

    def work() -> None:
        try:
            games = analysis.games(settings)
        except Exception as error:  # The top screen must stay usable.
            in_main_thread(_failed)(counting, str(error) or type(error).__name__)
            return
        in_main_thread(_choose_games)(counting, settings, analysis, games)

    threading.Thread(target=work, daemon=True).start()


def _counting_dialog() -> Popup:
    """Make the dialog shown while the games are counted (it has no button: it closes by itself)."""
    label = fitting_label(dp(28), halign="center")
    label.text = texts.text("analysis_counting")
    return Popup(
        title=texts.text("analysis_title"),
        title_size=sp(18),
        content=label,
        size_hint=(0.5, None),
        height=dp(140),
        auto_dismiss=False,
        background="",
        background_color=theme.BACKGROUND_COLOR,
        separator_color=theme.BUTTON_COLOR,
    )


def _failed(counting: Popup, reason: str) -> None:
    """Tell that the games could not be read."""
    counting.dismiss()
    show_message(texts.text("error_title"), reason)


def _choose_games(counting: Popup, settings: AppSettings, analysis: FolderAnalysis, games: FolderGames) -> None:
    """Show the list of the games to choose the ones to analyze, or only tell why there is none."""
    counting.dismiss()
    problem = texts.analysis_folder_problem(games)
    if problem:
        show_message(texts.text("analysis_title"), problem)
        return
    AnalysisChooser(games, settings.analysis, lambda chosen: _start(settings, analysis, chosen)).open()


def _start(settings: AppSettings, analysis: FolderAnalysis, chosen: list[Path]) -> None:
    """Analyze the chosen games, showing the progress."""

    def run(listener: AnalysisListener, stop: threading.Event) -> AnalysisSummary:
        return analysis.run(settings, chosen, listener, stop)

    AnalysisPopup(run).start()
