"""Everything the screens need, made by the app from the settings (see app.main).

The screens get it as one ScreenSetup, so that they need not know how it is made: the app
makes it again when the settings are saved (see gui.kentogo_app.KentoGoApp.use_setup).
"""

from __future__ import annotations

from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path

from kentogo.answers import QuizAnswers
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.engines import Engines
from kentogo.fight_setup import FightTools
from kentogo.fights_today import FightSummary, TodayFights
from kentogo.katago.evaluate import AnalysisEngine, EvaluationSettings
from kentogo.katago.startup import StartTimes
from kentogo.notice import Notice
from kentogo.quiz.collect import Progress
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.limit_offer import LimitOffer
from kentogo.quiz.quiz_run import Judging
from kentogo.quiz.ratio_offer import RatioOffer
from kentogo.quiz.transform import BoardTransform
from kentogo.report import Report, TodaySummary
from kentogo.seichi.seichi_plan import SeichiGame, SeichiQueue
from kentogo.seichi.seichi_settings import SeichiSettings
from kentogo.today import TodayProblems


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
        answers: Where the answers of the quiz are kept.
        analyze_games: Starts the analysis of the games with KataGo (the top screen's "KataGoで棋譜解析").
        notices: Problems found at the start, shown in a dialog on the top screen.
        use_seichi: Show the territory counting practice on the top screen.
        games_folder: Finds the games folder, as (folder, problem) (see games_folder.find_games_folder).
        seichi: The settings of the territory counting practice.
        plan_seichi: Plans the games of the territory counting practice from a games folder (called in a
            background thread).
        save_seichi_result: Keeps how the counting of a game went.
        save_language: Keeps the chosen language in the settings file. Returns "" when it is saved,
            or why it could not be saved.
        commentary: What the screens of the AI commentary need, or None (no AI commentary).
        start_times: The times that KataGo took to load before (shown while it loads).
        ratio_offer: Returns the offer to raise or lower the pass ratio, or None (see quiz.ratio_offer).
        answer_ratio_offer: Saves the user's answer to the offer (True: change the ratio).
        limit_offer: Returns the offer to set or lower the limit of a correct answer's loss, or None
            (see quiz.limit_offer).
        answer_limit_offer: Saves the user's answer to that offer (True: change the limit).
        report: Makes the report (成績表) from the games and the history (called in a background thread).
        today_summary: Makes the summary of the day, or None if nothing was answered today (in a background thread).
        judging: Returns what the quiz needs from a running KataGo (see quiz.quiz_run.Judging).
        load_fights: Makes today's local fight problems (called in a background thread).
        fight_summary: Makes the summary of the fights answered today from the IDs of all the current fights, or
            None if none was answered (in a background thread).
        fight_tools: Makes what the screen of the local fights uses, given the running KataGo and how it analyzes
            the positions (see kentogo.fight_setup).
    """

    load: Callable[[Progress], TodayProblems]
    policy: ScoringPolicy
    choose_transform: Callable[[], BoardTransform]
    engines_for: Callable[[Engines | None], Engines]
    open_settings: Callable[[str], None]
    answers: QuizAnswers
    analyze_games: Callable[[], None] = lambda: None
    notices: tuple[Notice, ...] = ()
    use_seichi: bool = False
    games_folder: Callable[[], tuple[Path | None, Notice | None]] = lambda: (None, None)
    seichi: SeichiSettings = SeichiSettings()
    plan_seichi: Callable[[Path], SeichiQueue] = lambda _folder: SeichiQueue([], None)
    save_seichi_result: Callable[[SeichiGame, bool], None] = lambda _game, _good: None
    save_language: Callable[[str], str] = lambda _language: ""
    commentary: CommentaryWorkspace | None = None
    start_times: StartTimes = StartTimes(None)
    ratio_offer: Callable[[], RatioOffer | None] = lambda: None
    answer_ratio_offer: Callable[[RatioOffer, bool], None] = lambda _offer, _yes: None
    limit_offer: Callable[[], LimitOffer | None] = lambda: None
    answer_limit_offer: Callable[[LimitOffer, bool], None] = lambda _offer, _yes: None
    report: Callable[[], Report] = Report
    today_summary: Callable[[], TodaySummary | None] = lambda: None
    judging: Callable[[Engines], Judging] = lambda _engines: Judging()
    load_fights: Callable[[], TodayFights] = lambda: TodayFights([])
    fight_summary: Callable[[Set[str]], FightSummary | None] = lambda _fight_ids: None
    fight_tools: Callable[[AnalysisEngine, EvaluationSettings], FightTools] = lambda _engine, _evaluation: FightTools(
        lambda _fight: None, lambda _run: None
    )
