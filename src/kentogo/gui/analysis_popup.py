"""The dialog that analyzes the games of the analysis's folder (the "KataGoで棋譜を解析" button of the settings).

The analysis runs in a background thread (see analysis_run); the dialog shows which game is
analyzed, the progress of its steps, and how each game ended. "中止" stops after the game that
is being analyzed. The dialog can be closed only when the run has ended.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from kentogo.analysis_run import AnalysisListener, AnalysisPlan, AnalysisSummary
from kentogo.app_settings import AppSettings
from kentogo.gui import texts, theme
from kentogo.gui.widgets import fitting_label, flat_button, growing_label, in_main_thread

SPACING = 8  # dp
BUTTON_HEIGHT = 44  # dp

# Analyzes the games, telling the listener; stops after the current game when the event is set.
AnalysisRun = Callable[[AnalysisListener, threading.Event], AnalysisSummary]


@dataclass(frozen=True)
class FolderAnalysis:
    """What the settings screen needs to analyze the games of the analysis's folder.

    Attributes:
        plan: Returns what a run with the settings would do (the folder and the numbers of games).
        run: Analyzes the games with the settings, telling the listener; stops when the event is set.
            The last argument is True when the games analyzed by KaTrain are analyzed again for
            KentoGo (see analysis_run.needs_kentogo_analysis).
    """

    plan: Callable[[AppSettings], AnalysisPlan]
    run: Callable[[AppSettings, AnalysisListener, threading.Event, bool], AnalysisSummary]


class AnalysisPopup(Popup):
    """The dialog of a run of the analysis."""

    def __init__(self, run: AnalysisRun, **kwargs):
        """Make the dialog. Call start() to open it and start the run."""
        super().__init__(
            title=texts.text("analysis_title"),
            title_size=sp(18),
            size_hint=(0.7, 0.7),
            auto_dismiss=False,
            background="",
            background_color=theme.BACKGROUND_COLOR,
            separator_color=theme.BUTTON_COLOR,
            **kwargs,
        )
        self._run = run
        self._stop = threading.Event()
        self.game_label = fitting_label(dp(28))
        self.step_label = fitting_label(dp(28))
        self.log_label = growing_label()
        log = ScrollView(do_scroll_x=False)
        log.add_widget(self.log_label)
        self.stop_button = flat_button(texts.text("analysis_stop"), self.stop)
        self.close_button = flat_button(texts.text("close"), self.dismiss, disabled=True)
        buttons = BoxLayout(size_hint_y=None, height=dp(BUTTON_HEIGHT), spacing=dp(SPACING))
        buttons.add_widget(self.stop_button)
        buttons.add_widget(self.close_button)
        content = BoxLayout(orientation="vertical", spacing=dp(SPACING), padding=dp(SPACING))
        for widget in (self.game_label, self.step_label, log, buttons):
            content.add_widget(widget)
        self.content = content

    def start(self) -> None:
        """Open the dialog and start the run in a background thread."""
        self.open()
        self.game_label.text = texts.text("analysis_starting")
        listener = AnalysisListener(
            in_main_thread(self._game_started), in_main_thread(self._progress), in_main_thread(self._game_finished)
        )

        def work() -> None:
            """Run the analysis (in the background thread)."""
            try:
                summary = self._run(listener, self._stop)
            except Exception as error:  # KataGo stopped, or a file cannot be read: tell it, do not crash.
                summary = AnalysisSummary(problem=str(error) or type(error).__name__)
            in_main_thread(self._finished)(summary)

        threading.Thread(target=work, daemon=True).start()

    def stop(self) -> None:
        """Ask the run to stop after the game that is being analyzed."""
        self._stop.set()
        self.stop_button.disabled = True
        self.step_label.text = texts.text("analysis_stopping")

    def _game_started(self, number: int, total: int, name: str) -> None:
        self.game_label.text = texts.text("analysis_game", number=number, total=total, name=name)
        self.step_label.text = ""

    def _progress(self, step: str, done: int, total: int) -> None:
        if not self._stop.is_set():
            self.step_label.text = texts.analysis_step_text(step, done, total)

    def _game_finished(self, name: str, outcome: str, detail: str) -> None:
        line = texts.analysis_outcome_text(name, outcome, detail)
        self.log_label.text = f"{self.log_label.text}\n{line}".strip("\n")

    def _finished(self, summary: AnalysisSummary) -> None:
        """Tell how the run ended, and let the dialog be closed."""
        self.game_label.text = texts.analysis_summary_text(summary)
        self.step_label.text = ""
        self.stop_button.disabled = True
        self.close_button.disabled = False
