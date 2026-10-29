"""Everything the screens need, made by the app from the settings (see app.main).

The screens get it as one ScreenSetup, so that they need not know how it is made: the app
makes it again when the settings are saved (see gui.kentogo_app.KentoGoApp.use_setup).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.engines import Engines
from kentogo.katago.startup import StartTimes
from kentogo.notice import Notice
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.transform import BoardTransform
from kentogo.review.history import AnswerHistory
from kentogo.seichi.seichi_history import SeichiHistory
from kentogo.seichi.seichi_settings import SeichiSettings
from kentogo.today import Progress, TodayProblems


@dataclass(frozen=True)
class ScreenSetup:
    """Everything the screens need, made before the window opens.

    KataGo is not started here: the app starts it when its window has opened (engines_for), and
    closes it when it ends.

    Attributes:
        load: Makes today's problems (called in a background thread by the start screen).
            It is told a function to report the progress.
        policy: The rule for judging answers.
        choose_transform: A function that returns how to change each problem.
        engines_for: Returns KataGo for these settings, given the KataGo that runs now or None
            (see the function engines_for).
        open_settings: A function that opens a settings screen, given one of settings_form.PAGES.
        history: Where the answers are saved, or None.
        notices: Problems found at the start, shown in a dialog on the top screen.
        use_seichi: Show the territory counting practice on the top screen.
        games_folder: Finds the games folder, as (folder, problem) (see today.find_games_folder).
        seichi: The settings of the territory counting practice.
        seichi_history: Where the results of the territory counting practice are saved, or None.
        save_language: Keeps the chosen language in the settings file. Returns "" when it is saved,
            or why it could not be saved.
        commentary: What the screens of the AI commentary need, or None (no AI commentary).
        start_times: The times that KataGo took to load before (shown while it loads).
    """

    load: Callable[[Progress], TodayProblems]
    policy: ScoringPolicy
    choose_transform: Callable[[], BoardTransform]
    engines_for: Callable[[Engines | None], Engines]
    open_settings: Callable[[str], None]
    history: AnswerHistory | None
    notices: tuple[Notice, ...] = ()
    use_seichi: bool = False
    games_folder: Callable[[], tuple[Path | None, Notice | None]] = lambda: (None, None)
    seichi: SeichiSettings = SeichiSettings()
    seichi_history: SeichiHistory | None = None
    save_language: Callable[[str], str] = lambda _language: ""
    commentary: CommentaryWorkspace | None = None
    start_times: StartTimes = StartTimes(None)
