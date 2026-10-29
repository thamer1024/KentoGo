"""The Kivy application: the top screen first, then the screen of the practice chosen there.

The top screen (see gui.top_screen) is shown at every start. From it, the quiz opens with
its start screen (which reads the games), and the territory counting practice (seichi),
when it is turned on in the settings, shows the final positions of games that ended by
counting, one after another, chosen and ordered as its settings say (see
seichi.seichi_plan); the user says how each counting went. Each screen has a button to
come back to the top screen.

KataGo is started with the app, as in KaTrain: when the window has opened, the main model is
loaded, then the comparison model, while a dialog tells how long it may still take (see
gui.loading_dialog). It runs until the app ends, for the quiz and the screen that shows the
games. When the settings change the program, the model or KataGo's settings file, it is
started again when the top screen is shown next.

A flag (on the start screen or in the menu) changes the language of all screens at
once, as in KaTrain, and the language is kept in the settings file for the next start.

Settings saved on a settings screen are used at once (see use_setup): a practice that is open
keeps the settings it was opened with, and the new ones are used when a practice is opened next.
"""

from __future__ import annotations

import sys
import threading
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView

from kentogo.gui import texts, theme
from kentogo.gui.api_screen import ApiScreen
from kentogo.gui.batch_screen import BatchScreen
from kentogo.gui.commentary_menu import CommentaryMenu
from kentogo.gui.dialogs import show_message
from kentogo.gui.fonts import register_font
from kentogo.gui.loading_dialog import LoadingDialog
from kentogo.gui.paste_screen import PasteScreen
from kentogo.gui.quiz_screen import QuizScreen
from kentogo.gui.seichi_screen import SeichiScreen
from kentogo.gui.splash_screen import SplashScreen
from kentogo.gui.top_screen import TopScreen
from kentogo.gui.viewer_screen import ViewerScreen
from kentogo.gui.widgets import in_main_thread, relabel_all, set_text, wrapping_label
from kentogo.katago.evaluate import Models
from kentogo.katago.startup import Loading
from kentogo.mistakes.problem import Problem
from kentogo.seichi.seichi_plan import SeichiGame, SeichiQueue, queue_from_history
from kentogo.today import TodayProblems
from kentogo.version import app_version

if TYPE_CHECKING:
    from kentogo.engines import Engines
    from kentogo.screen_setup import ScreenSetup


class KentoGoApp(App):
    """The Kivy application.

    Attributes:
        quiz: The quiz screen, or None before it is opened.
    """

    title = "KentoGo"
    icon = str(theme.APP_ICON)  # Shown on the window, the task bar (Windows) and the Dock (macOS).

    def __init__(self, setup: ScreenSetup, **kwargs):
        """Prepare the app.

        Args:
            setup: Everything the screens need (see app.ScreenSetup).
            **kwargs: Kivy's App arguments.
        """
        super().__init__(**kwargs)
        self.setup = setup
        self.quiz: QuizScreen | None = None
        self.engines: Engines | None = None  # KataGo, from the start of the app until it ends.
        self.engines_outdated = True  # True until KataGo runs with the settings of the setup.
        self.seichi_queue: SeichiQueue | None = None  # The games of the seichi practice in this start.
        self.frame: BoxLayout | None = None

    def build(self):
        """Show the top screen, and start KataGo a moment later, when the window has been made."""
        self.frame = BoxLayout()
        self.frame.add_widget(TopScreen(self._choices(), self.setup.open_settings, app_version()))
        Clock.schedule_once(lambda _dt: self._start())
        return self.frame

    def _start(self) -> None:
        """Tell the problems found at the start, and start KataGo."""
        if self.setup.notices:
            show_message(texts.text("notice_title"), texts.notices_text(self.setup.notices))
        self.start_engines()

    def start_engines(self) -> None:
        """Start KataGo with the settings of the setup (unless it runs with them), and show its loading.

        KataGo that runs with the same command lines is kept (see app.engines_for). The problems
        found when it was started are shown when the loading is done.
        """
        running = self.engines
        self.engines = self.setup.engines_for(running)
        self.engines_outdated = False
        if running is not None and self.engines.processes == running.processes:
            return  # Only the numbers of visits changed.
        engines = self.engines
        loading = Loading(engines.loading_stages(), self.setup.start_times)
        LoadingDialog(loading, lambda: self._loaded(engines)).open()

    def _loaded(self, engines: Engines) -> None:
        """Tell the problems found when KataGo was started (if they are still those of the running KataGo)."""
        if engines.notices and engines is self.engines:
            show_message(texts.text("notice_title"), texts.notices_text(engines.notices))

    def show_top(self) -> None:
        """Show the top screen, with a button for each practice that can be chosen.

        KataGo is started again here when the settings have changed it (no practice uses it now).
        """
        self.frame.clear_widgets()
        self.frame.add_widget(TopScreen(self._choices(), self.setup.open_settings, app_version()))
        if self.engines_outdated:
            self.start_engines()

    def _choices(self) -> list:
        """Return the practices of the top screen, as (text key, action)."""
        choices = [("mode_quiz", self.show_splash), ("mode_viewer", self.show_viewer)]
        if self.setup.commentary is not None:
            choices.append(("mode_commentary", self.show_commentary_menu))
        if self.setup.use_seichi:
            choices.append(("mode_seichi", self.show_seichi))
        return choices

    def use_setup(self, setup: ScreenSetup) -> None:
        """Use the setup made from new settings (saved on a settings screen) from now on.

        A practice that is open keeps the settings it was opened with; KataGo follows the new
        settings when the top screen is shown next (see start_engines). The games of the
        territory counting practice are planned again, and the top screen is made again, so
        that its buttons follow the settings.
        """
        self.setup = setup
        self.engines_outdated = True
        self.seichi_queue = None
        if self.frame is not None and any(isinstance(child, TopScreen) for child in self.frame.children):
            self.show_top()

    def show_viewer(self) -> None:
        """Show the screen that shows the games of the games folder move by move."""
        folder, problem = self.setup.games_folder()
        if folder is None:
            show_message(texts.text("mode_viewer"), texts.notice_text(problem), on_close=self.show_top)
            return
        self.frame.clear_widgets()
        models = self.engines.viewer_models() if self.engines is not None else Models()
        self.frame.add_widget(ViewerScreen(folder, on_back=self.show_top, models=models))

    def show_commentary_menu(self) -> None:
        """Show the menu of the AI commentary."""
        self.frame.clear_widgets()
        choices = [
            ("commentary_batch", lambda: self._show_commentary_screen(BatchScreen)),
            ("commentary_api", lambda: self._show_commentary_screen(ApiScreen)),
            ("commentary_paste", lambda: self._show_commentary_screen(PasteScreen)),
        ]
        self.frame.add_widget(CommentaryMenu(choices, on_back=self.show_top))

    def _show_commentary_screen(self, screen: type) -> None:
        """Show a screen of the AI commentary (PasteScreen, ApiScreen or BatchScreen) for the games folder."""
        folder, problem = self.setup.games_folder()
        if folder is None:
            show_message(texts.text("mode_commentary"), texts.notice_text(problem), on_close=self.show_commentary_menu)
            return
        self.frame.clear_widgets()
        self.frame.add_widget(screen(self.setup.commentary, folder, on_back=self.show_commentary_menu))

    def open_game(self, problem: Problem) -> None:
        """Show the game of a quiz problem at the mistake, over the quiz screen (closing it goes back to the quiz)."""
        view = ModalView(size_hint=(1, 1), auto_dismiss=False, background="", background_color=theme.BACKGROUND_COLOR)
        models = self.engines.viewer_models() if self.engines is not None else Models()
        viewer = ViewerScreen(None, on_back=view.dismiss, back_label="close", models=models)
        view.add_widget(viewer)
        view.open()
        viewer.open_game(Path(problem.sgf_path), problem.move_number)

    def show_seichi(self) -> None:
        """Start (or go on with) the territory counting practice: find the next game, in the background.

        The games of this start of the app are planned once (see seichi_plan), when the practice
        is first chosen; going back to the choice and coming again goes on with the same plan.
        """
        folder, problem = self.setup.games_folder()
        if folder is None:
            show_message(texts.text("mode_seichi"), texts.notice_text(problem), on_close=self.show_top)
            return
        self.frame.clear_widgets()
        searching = wrapping_label(halign="center", valign="middle")
        set_text(searching, texts.lazy("seichi_searching"))
        self.frame.add_widget(searching)

        def work() -> None:
            """Plan the games (the first time) and read the next one in the background thread."""
            try:
                if self.seichi_queue is None:
                    setup = self.setup
                    self.seichi_queue = queue_from_history(folder, setup.seichi, setup.seichi_history, date.today())
                game = self.seichi_queue.next_game()
            except Exception as error:  # For example, the folder cannot be read.
                in_main_thread(self._seichi_failed)(str(error))
                return
            in_main_thread(self._show_seichi_game)(game)

        threading.Thread(target=work, daemon=True).start()

    def _show_seichi_game(self, game: SeichiGame | None) -> None:
        """Show the final position of the next game, or tell why there is none."""
        self.frame.clear_widgets()
        queue = self.seichi_queue
        if game is None:
            if queue.finished:
                message = texts.text("seichi_session_done", count=queue.today_count)
            elif queue.counted:
                message = texts.text("seichi_none_left", count=queue.counted)
            else:
                message = texts.text("seichi_no_game")
            show_message(texts.text("mode_seichi"), message, on_close=self.show_top)
            return
        number, most = queue.today_count + 1, queue.limit

        def progress() -> str:
            """Return the line about this game: its number today, the most games a day, and whether it is a review."""
            limit = texts.text("seichi_progress_limit", limit=most) if most else ""
            review = texts.text("seichi_progress_review") if game.review else ""
            return texts.text("seichi_progress", number=number, limit=limit, review=review)

        screen = SeichiScreen(
            game.game,
            on_back=self._back_to_choice,
            on_judged=lambda good: self._seichi_judged(game, good),
            progress=progress,
            step_seconds=self.setup.seichi.step_seconds,
        )
        self.frame.add_widget(screen)

    def _seichi_judged(self, game: SeichiGame, good: bool) -> None:
        """Save how the counting of a game went, and go on to the next game."""
        if self.setup.seichi_history is not None:
            self.setup.seichi_history.save(game.problem_id, str(game.game.path), good)
        if self.seichi_queue is not None:  # None when the settings were saved: it is planned again.
            self.seichi_queue.count_one()
        self.show_seichi()

    def _seichi_failed(self, message: str) -> None:
        """Tell that the games could not be read, and go back to the top screen."""
        self.frame.clear_widgets()
        show_message(texts.text("error_title"), message, on_close=self.show_top)

    def _back_to_choice(self) -> None:
        """Leave the territory counting screen, and go back to the top screen."""
        self.show_top()

    def show_splash(self) -> None:
        """Show the start screen, and read the games in the background (KataGo runs already)."""
        if self.engines is None:  # Chosen before KataGo was started (just after the window opened).
            self.start_engines()
        self.frame.clear_widgets()
        splash = SplashScreen(on_start=self.show_quiz, on_back=self.show_top)
        self.frame.add_widget(splash)
        splash.load(self.setup.load)

    def show_quiz(self, today: TodayProblems) -> None:
        """Replace the start screen with the quiz screen."""
        setup, engines = self.setup, self.engines
        self.frame.clear_widgets()
        self.quiz = QuizScreen(
            today.problems,
            setup.policy,
            setup.choose_transform,
            engines.judging(),
            texts.notice_text(today.message),
            setup.history,
            on_back=self._leave_quiz,
            open_game=self.open_game,
        )
        self.frame.add_widget(self.quiz)

    def change_language(self, language: str) -> None:
        """Show all screens in another language at once, and keep the language for the next start.

        Args:
            language: One of texts.LANGUAGES.
        """
        if language == texts.language():
            return
        try:
            texts.set_language(language)
        except OSError as error:  # The file of the language is missing: stay in the language used now.
            show_message(texts.text("error_title"), str(error))
            return
        register_font(language)
        relabel_all()
        problem = self.setup.save_language(language)
        if problem:
            show_message(texts.text("error_title"), texts.text("notice_language_not_saved", reason=problem))

    def stop_engines(self) -> None:
        """Close KataGo (when the app closes)."""
        if self.engines is not None:
            self.engines.close()
            print("KataGo stopped", file=sys.stderr)
            self.engines = None

    def _leave_quiz(self) -> None:
        """Leave the quiz: save the answers KataGo is still judging, and go back to the top screen."""
        if self.quiz is not None:
            self.quiz.close()
            self.quiz = None
        self.show_top()
