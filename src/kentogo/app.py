"""Start KentoGo: read the settings, open the start screen, and then the quiz screen.

Usage:
    python -m kentogo.app [GAMES_FOLDER] [options]

The settings are read from ~/.kentogo/settings.json (see settings_file). If the
file does not exist, it is made with the default values, so that the user can
change them. Changes saved on the settings screens are used at once (see gui.kentogo_app).

The games folder is taken from the settings. A folder given on the command line
is used instead, for this start only. Without a folder, the app still starts and
tells the user to set the folder on the settings screen.

Answers are saved to history.sqlite3 in the same folder as the settings file.
The problems made from each SGF file are kept in problem_cache.sqlite3 there
too, so that only new and changed files are read at the next start.
The history decides today's problems: problems never answered, and reviews of
problems answered wrong whose day has come (see today.py). The start screen
reads the games in the background and shows how many problems there are today.

The menu button of the top screen opens the settings screens, which save to
the same file.

The screens are in English at the first start. The flags of the languages (on the
start screen and in the menu, as in KaTrain) change the language at once, and it is
kept in the "general" section of the same file.

KataGo is started with the "engine" part of the settings, and is used to judge
answers whose loss is not in the SGF file. When the settings file is made for the
first time, the engine settings are copied from KaTrain's config.json.
The main KataGo and the KataGo with the comparison model get one query at a
time between them (see katago.one_at_a_time), so that they do not share the GPU.
KataGo is started with the app, as in KaTrain (the main model first, then the
comparison model), and closed when the app closes; it is started again only when the
settings change its command line (see engines_for). The territory counting practice
does not use KataGo.

With --test-quiz loss or --test-quiz punish, the app asks every problem of that kind of the games
analyzed by KentoGo, to try them out; the answers are not saved (see quiz_trial).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from kentogo.analysis_run import list_games, run_analysis
from kentogo.app_settings import AppSettings, without_offer_answers
from kentogo.clear_history import clear_answers, clear_seichi_results
from kentogo.commentary.prompt_text import create_user_prompt_file
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.engines import Engines, engines_for, measure_katago_speed
from kentogo.gui import texts
from kentogo.gui.commentary_texts import commentary_language
from kentogo.katago.startup import TIMES_FILE, StartTimes
from kentogo.notice import Notice
from kentogo.opengl_fallback import OldOpenGLError, install_check, start_again_with_angle
from kentogo.opponent_rank import problem_ranks
from kentogo.quiz.limit_offer import LimitOffer, find_limit_offer
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.quiz.ratio_offer import RatioOffer, find_ratio_offer, judged, may_ask
from kentogo.quiz.transform import BoardTransform, random_transform
from kentogo.quiz_trial import TRIAL_KINDS, trial_loader
from kentogo.report import load_report, load_today_summary
from kentogo.review.history import AnswerHistory
from kentogo.review.record import AnswerRecord
from kentogo.screen_setup import ScreenSetup
from kentogo.seichi.seichi_history import SeichiHistory, open_seichi_history
from kentogo.settings import SettingsStore
from kentogo.settings_file import SETTINGS_PATH, default_settings, load_settings, save_settings
from kentogo.system_open import open_with_system
from kentogo.today import (
    NoGamesFolderError,
    Progress,
    TodayProblems,
    exclude_all_problems,
    find_games_folder,
    include_all_problems,
    load_today,
    open_history,
)

# The window size when the app starts, and the smallest size that the user can make it.
# 1280x800 fits the screen of a 13-inch MacBook and most laptops.
WINDOW_SIZE = (1280, 800)
MINIMUM_WINDOW_SIZE = (1024, 680)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Read the command line arguments.

    Args:
        argv: The arguments, without the program name.

    Returns:
        The values of the arguments.
    """
    parser = argparse.ArgumentParser(prog="kentogo", description="Practice the big mistakes in your games.")
    parser.add_argument(
        "folder", type=Path, nargs="?", help="folder with SGF files (instead of the one in the settings)"
    )
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH, help="the settings file to use")
    parser.add_argument("--no-katago", action="store_true", help="do not start KataGo, for this start only")
    parser.add_argument(
        "--test-quiz",
        choices=TRIAL_KINDS,
        help="ask every problem of this kind of the games analyzed by KentoGo, without saving the answers",
    )
    return parser.parse_args(argv)


def read_language(path: Path) -> str:
    """Return the language in the "general" section of the settings file (English if it has none).

    A broken file or an unknown language gives English, so that the app always starts.

    Args:
        path: Path of the settings file. "~" means the home folder.
    """
    store = SettingsStore(path.expanduser(), {})
    try:
        store.load()
    except ValueError:
        return texts.DEFAULT_LANGUAGE
    language = store.section("general").get("language")
    return language if language in texts.LANGUAGES else texts.DEFAULT_LANGUAGE


def save_language(path: Path, language: str) -> str:
    """Keep the language in the "general" section of the settings file. The other sections are kept.

    Args:
        path: Path of the settings file. "~" means the home folder.
        language: One of texts.LANGUAGES.

    Returns:
        "" when it is saved, or why it could not be saved (the file is broken or cannot be written).
    """
    store = SettingsStore(path.expanduser(), {})
    try:
        store.load()
        store.set_section("general", {**store.section("general"), "language": language})
        store.save()
    except (ValueError, OSError) as error:
        return str(error)
    return ""


def _settings_or_defaults(path: Path, notices: list[Notice]) -> AppSettings:
    """Read the settings file. If it is broken, use the default values and tell the user.

    The app still starts, so that the settings can be fixed on the settings screen.

    Args:
        path: Path of the settings file.
        notices: A message for the user is added here when the file is broken.
    """
    try:
        return load_settings(path)
    except ValueError as error:
        print(f"cannot use the settings: {error}", file=sys.stderr)
        notices.append(Notice("notice_settings_broken", {"reason": error}))
        return AppSettings.from_sections(default_settings())


def _current_settings(path: Path, started_with: AppSettings) -> AppSettings:
    """Read the settings from the file (they may have been saved after the start).

    If the file cannot be read, the settings read at the start are used.
    """
    try:
        return load_settings(path)
    except ValueError:
        return started_with


def _open_prompt_file(settings_path: Path) -> Path:
    """Make the user's prompt file of the AI commentary if it does not exist, open it, and return its path.

    The file is the one of the prompt used in the language of the screens now (see commentary.language).

    Raises:
        OSError: If the file cannot be made or opened.
    """
    path = create_user_prompt_file(settings_path, commentary_language().prompt)
    open_with_system(path)
    return path


def _exclude_all(settings_path: Path, folder_argument: Path | None, quiz: QuizSettings) -> int:
    """Set aside all problems (see today.exclude_all_problems); a missing games folder is told in words.

    Raises:
        ValueError: If there is no games folder (the message tells why, in the language of the screens).
    """
    try:
        return exclude_all_problems(settings_path, folder_argument, quiz)
    except NoGamesFolderError as error:
        raise ValueError(texts.notice_text(error.notice)) from error


def _clear_answers(settings_path: Path, started_with: AppSettings) -> Path:
    """Clear the history of answers after a backup (see clear_history), and forget when the offers were answered.

    Without the second step, the offers would not come again until there are as many new answers as
    there were before (see app_settings.without_offer_answers).

    Returns:
        The path of the backup.
    """
    backup = clear_answers(settings_path, datetime.now())
    save_settings(settings_path, without_offer_answers(_current_settings(settings_path, started_with)))
    return backup


class _SeichiHistoryOpener:
    """Opens the history of the territory counting practice when it is first used, and closes it at the end.

    The practice may be turned on in the settings after the start, so the history is opened then.
    """

    def __init__(self, settings_path: Path):
        """Remember where the settings file is (the history is next to it)."""
        self._settings_path = settings_path
        self._tried = False
        self.history: SeichiHistory | None = None

    def open(self, notices: list[Notice]) -> SeichiHistory | None:
        """Open the history the first time (a problem is added to notices), and return it (None if it failed)."""
        if not self._tried:
            self._tried = True
            self.history, problem = open_seichi_history(self._settings_path)
            if problem:
                notices.append(Notice("notice_seichi_history_failed", {"reason": problem}))
        return self.history

    def close(self) -> None:
        """Close the history if it was opened."""
        if self.history is not None:
            self.history.close()


def main(argv: list[str] | None = None) -> None:
    """Read the arguments and the settings, and open the window.

    Settings saved on a settings screen are used at once: the setup of the screens is made again
    from them (see gui.kentogo_app.KentoGoApp.use_setup).
    """
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    notices: list[Notice] = []  # Shown on the start screen, because the user does not look at the console.
    language = read_language(arguments.settings)
    texts.set_language(language)  # Before any text is made, so that the notices are in this language too.
    settings = _settings_or_defaults(arguments.settings, notices)
    rng = random.Random()
    # Used by the quiz screen to save the answers (not in a trial: see quiz_trial).
    history = None if arguments.test_quiz else open_history(arguments.settings, notices)
    seichi = _SeichiHistoryOpener(arguments.settings)

    def make_setup(current: AppSettings, shown: list[Notice]) -> ScreenSetup:
        """Make the setup of the screens from some settings."""
        seichi_history = seichi.open(shown) if current.seichi.use_seichi else None
        parts = _SetupParts(arguments, current, history, seichi_history, rng, tuple(shown))
        return _make_setup(parts, lambda saved: _use_new_setup(make_setup(saved, [])))

    setup = make_setup(settings, notices)
    try:
        _run_app(setup, language)
    finally:
        if history is not None:
            history.store.close()
        seichi.close()


@dataclass(frozen=True)
class _SetupParts:
    """What the setup of the screens is made from (see _make_setup)."""

    arguments: argparse.Namespace
    settings: AppSettings
    history: AnswerHistory | None
    seichi_history: SeichiHistory | None
    rng: random.Random
    notices: tuple[Notice, ...]


def _make_setup(parts: _SetupParts, on_saved: Callable[[AppSettings], None]) -> ScreenSetup:
    """Make everything the screens need from the settings.

    Args:
        parts: The arguments, the settings, the histories, the random numbers and the notices.
        on_saved: Called with the new settings after they are saved on a settings screen.
    """
    arguments, settings, rng = parts.arguments, parts.settings, parts.rng

    def choose_transform() -> BoardTransform:
        """Choose how to change the next problem, as allowed by the settings."""
        return random_transform(rng, rotate=settings.quiz.rotate, swap_colors=settings.quiz.swap_colors)

    return ScreenSetup(
        _problem_loader(arguments, settings, rng),
        settings.quiz.scoring,
        choose_transform,
        lambda running: engines_for(running, settings.engine, arguments.no_katago),
        _settings_opener(arguments, settings, on_saved),
        parts.history,
        analyze_games=_analysis_starter(arguments, settings),
        notices=parts.notices,
        use_seichi=settings.seichi.use_seichi,
        games_folder=lambda: find_games_folder(arguments.folder, settings.quiz.games_folder),
        seichi=settings.seichi,
        seichi_history=parts.seichi_history,
        save_language=lambda chosen: save_language(arguments.settings, chosen),
        commentary=CommentaryWorkspace(
            arguments.settings,
            lambda: _current_settings(arguments.settings, settings).commentary,
            lambda: _current_settings(arguments.settings, settings).quiz.extract,
            tuple(settings.quiz.extract.my_names),
        ),
        start_times=StartTimes(arguments.settings.parent / TIMES_FILE),
        ratio_offer=_ratio_offer_maker(arguments.settings, settings, parts.history),
        answer_ratio_offer=_ratio_offer_saver(arguments.settings, settings, parts.history, on_saved),
        limit_offer=_limit_offer_maker(arguments.settings, settings, parts.history),
        answer_limit_offer=_limit_offer_saver(arguments.settings, settings, parts.history, on_saved),
        report=lambda: load_report(
            arguments.settings, arguments.folder, _current_settings(arguments.settings, settings)
        ),
        today_summary=lambda: load_today_summary(
            arguments.settings, arguments.folder, _current_settings(arguments.settings, settings), date.today()
        ),
        player_ranks=lambda problem: problem_ranks(arguments.settings, problem),
    )


def _problem_loader(
    arguments: argparse.Namespace, settings: AppSettings, rng: random.Random
) -> Callable[[Progress], TodayProblems]:
    """Return the function that makes the problems in the background thread of the start screen.

    They are today's problems, or the problems of the trial with --test-quiz (see quiz_trial).
    """
    if arguments.test_quiz:
        return trial_loader(arguments.settings, arguments.folder, settings, arguments.test_quiz)
    return lambda progress: load_today(arguments.settings, arguments.folder, settings, rng, progress)


def _judged_answers(history: AnswerHistory | None) -> list[AnswerRecord]:
    """Return the answers in the history that can be judged again, the oldest first."""
    if history is None:
        return []
    records = [record for records in history.all_previous().values() for record in records]
    return judged(sorted(records, key=lambda record: record.record_id or 0))


def _ratio_offer_maker(
    path: Path, started_with: AppSettings, history: AnswerHistory | None
) -> Callable[[], RatioOffer | None]:
    """Return the function that makes the offer to raise or lower the pass ratio, or None (see quiz.ratio_offer)."""

    def offer() -> RatioOffer | None:
        """Make the offer from the settings in the file and the latest answers."""
        quiz = _current_settings(path, started_with).quiz
        answers = _judged_answers(history)
        if not may_ask(quiz.ratio_offer, len(answers), quiz.ratio_asked_at, quiz.offer_window):
            return None
        return find_ratio_offer(answers, quiz.scoring, quiz.offer_window)

    return offer


def _ratio_offer_saver(
    path: Path, started_with: AppSettings, history: AnswerHistory | None, on_saved: Callable[[AppSettings], None]
) -> Callable[[RatioOffer, bool], None]:
    """Return the function that saves the answer to the offer, and uses the settings at once."""

    def answer(offer: RatioOffer, yes: bool) -> None:
        """Change the pass ratio (yes), and remember when the offer was answered (yes or no)."""
        current = _current_settings(path, started_with)
        quiz = replace(current.quiz, ratio_asked_at=len(_judged_answers(history)))
        if yes:
            quiz = replace(quiz, scoring=replace(quiz.scoring, pass_ratio=offer.proposed))
        new_settings = replace(current, quiz=quiz)
        save_settings(path, new_settings)
        on_saved(new_settings)

    return answer


def _limit_offer_maker(
    path: Path, started_with: AppSettings, history: AnswerHistory | None
) -> Callable[[], LimitOffer | None]:
    """Return the function that makes the offer of the limit of a correct answer's loss (see quiz.limit_offer)."""

    def offer() -> LimitOffer | None:
        """Make the offer from the settings in the file and the latest answers."""
        quiz = _current_settings(path, started_with).quiz
        answers = _judged_answers(history)
        if not may_ask(quiz.ratio_offer, len(answers), quiz.limit_asked_at, quiz.offer_window):
            return None
        return find_limit_offer(answers, quiz.scoring, quiz.offer_window, quiz.limit_steps)

    return offer


def _limit_offer_saver(
    path: Path, started_with: AppSettings, history: AnswerHistory | None, on_saved: Callable[[AppSettings], None]
) -> Callable[[LimitOffer, bool], None]:
    """Return the function that saves the answer to the offer of the limit, and uses the settings at once."""

    def answer(offer: LimitOffer, yes: bool) -> None:
        """Change the limit (yes), and remember when the offer was answered (yes or no)."""
        current = _current_settings(path, started_with)
        quiz = replace(current.quiz, limit_asked_at=len(_judged_answers(history)))
        if yes:
            quiz = replace(quiz, scoring=replace(quiz.scoring, max_answer_loss=offer.proposed))
        new_settings = replace(current, quiz=quiz)
        save_settings(path, new_settings)
        on_saved(new_settings)

    return answer


def _settings_opener(
    arguments: argparse.Namespace, settings: AppSettings, on_saved: Callable[[AppSettings], None]
) -> Callable[[str], None]:
    """Return the function that opens a settings screen (given one of settings_form.PAGES).

    Args:
        arguments: The command line arguments (the settings file and the games folder).
        settings: The settings used now, when the settings file cannot be read.
        on_saved: Called with the new settings after they are saved.
    """

    def save(new_settings: AppSettings) -> None:
        """Write the settings to the file, and use them at once."""
        save_settings(arguments.settings, new_settings)
        on_saved(new_settings)

    def open_settings(page: str) -> None:
        """Open a settings screen with the settings in the file."""
        from kentogo.gui.settings_popup import SettingsPopup

        SettingsPopup(
            _current_settings(arguments.settings, settings),
            save,
            exclude_all=lambda q: _exclude_all(arguments.settings, arguments.folder, q),
            include_all=lambda: include_all_problems(arguments.settings),
            clear_answers=lambda: _clear_answers(arguments.settings, settings),
            clear_seichi=lambda: clear_seichi_results(arguments.settings, datetime.now()),
            page=page,
            edit_prompt=lambda: _open_prompt_file(arguments.settings),
            measure=lambda: measure_katago_speed(
                _current_settings(arguments.settings, settings).engine, _running_engines()
            ),
        ).open()

    return open_settings


def _analysis_starter(arguments: argparse.Namespace, settings: AppSettings) -> Callable[[], None]:
    """Return the function that starts the analysis of the games with KataGo from the top screen.

    It uses the settings saved last, and the app's KataGo when it runs with them (see analysis_run).
    """

    def start() -> None:
        from kentogo.gui.analysis_popup import FolderAnalysis
        from kentogo.gui.analysis_start import start_folder_analysis

        analysis = FolderAnalysis(
            list_games,
            lambda saved, games, listener, stop: run_analysis(saved, _running_engines(), games, listener, stop),
        )
        start_folder_analysis(_current_settings(arguments.settings, settings), analysis)

    return start


def _running_engines() -> Engines | None:
    """Return the KataGo of the running app, or None (no app, or KataGo is not started)."""
    from kivy.app import App

    return getattr(App.get_running_app(), "engines", None)


def _use_new_setup(setup: ScreenSetup) -> None:
    """Give the running app the setup made from new settings (nothing happens without a running app)."""
    from kivy.app import App

    app = App.get_running_app()
    if app is not None:
        app.use_setup(setup)


# The name that Windows groups KentoGo's windows by on the task bar.
WINDOWS_APP_ID = "KentoGo.KentoGo"


def _use_own_taskbar_button() -> None:
    """On Windows, give KentoGo its own button on the task bar, so that it shows KentoGo's icon.

    Without this, Windows puts the window with the program that started it (python.exe, or the
    kentogo.exe that uv makes) and shows that program's icon. Call it before the window is made.
    """
    if sys.platform != "win32":
        return
    import ctypes

    with contextlib.suppress(AttributeError, OSError):  # Then the button keeps the starting program's icon.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)


def _run_app(setup: ScreenSetup, language: str) -> None:
    """Open the window with the start screen, and run Kivy until the window is closed.

    The start screen reads the games in the background and shows today's numbers.
    Its start button opens the quiz screen (see gui.kentogo_app). When the window is closed (or Kivy
    stops with an error), answers still waiting for KataGo are saved.

    Kivy is imported here, so that the rest of this module can be used (and tested)
    without Kivy. KIVY_NO_ARGS stops Kivy from reading our command line arguments.
    On Windows with only an old OpenGL, KentoGo is started again with ANGLE instead (see
    opengl_fallback), and this one ends.

    Args:
        setup: Everything the screens need.
        language: The language of the screens (one of texts.LANGUAGES), which chooses the font.
    """
    os.environ.setdefault("KIVY_NO_ARGS", "1")
    _use_own_taskbar_button()
    from kivy.config import Config

    # Without this, Kivy leaves a red circle where the right mouse button is clicked (the same as KaTrain).
    Config.set("input", "mouse", "mouse,multitouch_on_demand")
    # The smallest window size is given before the window is made. Setting Window.minimum_width and
    # Window.minimum_height one after the other makes Kivy warn, because one of them is still 0.
    Config.set("graphics", "minimum_width", str(MINIMUM_WINDOW_SIZE[0]))
    Config.set("graphics", "minimum_height", str(MINIMUM_WINDOW_SIZE[1]))
    # Esc returns from a sequence to the game on the game screen; it must not close the window.
    Config.set("kivy", "exit_on_escape", "0")

    install_check()
    try:
        from kivy.core.window import Window
    except OldOpenGLError:
        start_again_with_angle()
        return

    from kentogo.gui import theme
    from kentogo.gui.fonts import register_font
    from kentogo.gui.kentogo_app import KentoGoApp

    register_font(language)
    Window.clearcolor = theme.BACKGROUND_COLOR
    Window.size = WINDOW_SIZE

    app = KentoGoApp(setup)
    try:
        app.run()
    finally:
        if app.quiz is not None:
            app.quiz.save_unfinished()
        app.stop_engines()


if __name__ == "__main__":
    main()
