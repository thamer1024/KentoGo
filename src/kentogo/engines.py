"""KataGo for the app: start it, and measure its speed.

KataGo is started with the app, as in KaTrain, and closed when the app closes. It is started
again only when the settings change its command line (see engines_for): new numbers of visits
use the running process. Each query is sent to KataGo at once, as KaTrain does, with KaTrain's
time limit (see katago.timed_queries).

The screens get the process as Engines; they never start KataGo themselves.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace

from kentogo.katago.engine_settings import EngineSettings
from kentogo.katago.evaluate import AnalysisEngine, EvaluationSettings, Models
from kentogo.katago.locate import EngineCommand, KataGoNotFoundError, engine_command, katrain_package
from kentogo.katago.process import KataGoProcess
from kentogo.katago.speed import MeasuredSpeed, measure_speed, wait_for_answer
from kentogo.katago.startup import LoadingStage
from kentogo.katago.timed_queries import RunningQueries, TimedEngine
from kentogo.notice import Notice
from kentogo.quiz.quiz_run import Judging


def evaluation_settings(engine_settings: EngineSettings) -> EvaluationSettings:
    """Return how KataGo analyzes: the number of visits, the noise and the visits of 地と形勢 of the settings."""
    return EvaluationSettings(
        engine_settings.max_visits,
        engine_settings.wide_root_noise,
        engine_settings.estimate_visits,
        engine_settings.max_time,
    )


def make_command(engine_settings: EngineSettings) -> tuple[EngineCommand | None, EvaluationSettings, str]:
    """Make the command that starts KataGo, checking that its files exist.

    Returns:
        A tuple (command, settings, problem). command is None if a file is missing, and
        problem then tells why. settings has the number of visits and the noise.
    """
    settings = evaluation_settings(engine_settings)
    try:
        package = katrain_package(engine_settings.katrain_folder)
        command = engine_command(engine_settings.katrain_engine(), package)
    except KataGoNotFoundError as error:
        return None, settings, str(error)
    return command, settings, ""


def start_engine(engine_settings: EngineSettings) -> tuple[KataGoProcess | None, EvaluationSettings, str]:
    """Start KataGo with the engine settings.

    Returns:
        A tuple (engine, settings, problem). engine is None if KataGo could not be
        started, and problem then tells why. settings has the number of visits and the noise.
    """
    command, settings, problem = make_command(engine_settings)
    if command is None:
        return None, settings, problem
    process = KataGoProcess(command)
    try:
        process.start()
    except OSError as error:
        return None, settings, f"cannot start KataGo: {error}"
    # Shown so that the user can check which program, model and settings file are used.
    print("KataGo command: " + " ".join(command.command), file=sys.stderr)
    return process, settings, ""


def start_app_engine(
    engine_settings: EngineSettings, turned_off: bool, notices: list[Notice] | None = None
) -> tuple[KataGoProcess | None, EvaluationSettings, str]:
    """Start KataGo for the app, unless it is turned off.

    Args:
        engine_settings: The engine settings.
        turned_off: True if KataGo is turned off for this start (--no-katago).
        notices: If given, a message for the user is added when KataGo cannot be started
            (shown in a dialog, because the user does not look at the console).

    Returns:
        A tuple (engine, settings, problem). engine is None when it could not be started (problem tells why).
    """
    if turned_off or not engine_settings.use_katago:
        return None, EvaluationSettings(), "KataGo is turned off"
    engine, evaluation, problem = start_engine(engine_settings)
    print(problem or f"KataGo started ({evaluation.max_visits} visits)", file=sys.stderr)
    if problem and notices is not None:
        notices.append(Notice("notice_katago_failed", {"reason": problem}))
    return engine, evaluation, problem


@dataclass(frozen=True)
class Engines:
    """The KataGo process of the app, started with the app and closed when it ends (as in KaTrain).

    The quiz and the screen that shows the games use it. It is started again only when its
    command line changes (another program, model or settings file); a change of the numbers of
    visits uses the running process (see engines_for).

    Attributes:
        engine: KataGo (see katago.timed_queries), or None if it is not available.
        evaluation: How KataGo analyzes the positions.
        engine_problem: Why KataGo is not available ("" if it is available).
        notices: Problems found when it was started, to show the user.
        process: The process itself, to close it, or None.
        command: The command line it was started with (see engine_command_line).
    """

    engine: AnalysisEngine | None
    evaluation: EvaluationSettings
    engine_problem: str
    notices: tuple[Notice, ...] = ()
    process: KataGoProcess | None = None
    command: tuple | None = None

    def close(self) -> None:
        """Stop the KataGo process."""
        if self.process is not None:
            self.process.close()

    def loading_stages(self) -> list[LoadingStage]:
        """Return the KataGo process to wait for at the start (none when it is not running)."""
        return [] if self.process is None else [_main_stage(self.process)]

    def judging(self) -> Judging:
        """Return KataGo for the quiz: for judging the answers and showing sequences."""
        return Judging(self.engine, self.evaluation, self.engine_problem)

    def viewer_models(self) -> Models:
        """Return the models for the screen that shows the games (the main one, if it is running)."""
        return self.judging().models()


def _main_stage(main: KataGoProcess) -> LoadingStage:
    """Return the loading of the main KataGo."""
    return LoadingStage(
        "loading_main",
        " ".join(main.command.command),
        lambda: main.wait_until_ready(0),
        lambda: not main.is_running,
        lambda: main.ready_seconds,
    )


def open_engines(engine_settings: EngineSettings, turned_off: bool) -> Engines:
    """Start KataGo for the app (see start_app_engine). Problems are told in the notices.

    Each query is sent to KataGo at once, and the time of its answer is written (see timed_queries).
    """
    notices: list[Notice] = []
    command = engine_command_line(engine_settings, turned_off)
    engine, evaluation, problem = start_app_engine(engine_settings, turned_off, notices)
    timed = TimedEngine(engine, RunningQueries()) if engine is not None else None
    return Engines(timed, evaluation, problem, tuple(notices), engine, command)


def engine_command_line(engine_settings: EngineSettings, turned_off: bool) -> tuple | None:
    """Return the command line of KataGo (None when it is not used).

    A command line is the program with its arguments, and whether the shell runs it: not the
    number of visits, which each query sends.
    """
    if turned_off or not engine_settings.use_katago:
        return None
    command, _, _ = make_command(engine_settings)
    return None if command is None else (command.command, command.shell)


def engines_for(running: Engines | None, engine_settings: EngineSettings, turned_off: bool) -> Engines:
    """Return KataGo for some settings: the running process if it fits them, or a new one.

    The running process is kept when it was started with the same command line: only the
    numbers of visits and the noise change. Otherwise it is closed, and a new one is started.

    Args:
        running: The KataGo that runs now, or None.
        engine_settings: The engine settings.
        turned_off: True if KataGo is turned off for this start (--no-katago).
    """
    if running is not None and running.command == engine_command_line(engine_settings, turned_off):
        return replace(running, evaluation=evaluation_settings(engine_settings), notices=())
    if running is not None:
        running.close()
    return open_engines(engine_settings, turned_off)


def analysis_engine(engine_settings: EngineSettings, running: Engines | None) -> tuple[KataGoProcess | None, bool, str]:
    """Return the KataGo for analyzing games (see analysis_run): the app's one, or one of its own.

    The app's KataGo is used as it is when it runs with the settings: the analysis sends its
    queries at KaTrain's low priorities, so the quiz's queries are answered first. Otherwise a new
    KataGo is started (the caller waits until it is ready and stops it after the analysis).

    Returns:
        (engine, own, problem): own is True for a KataGo started here; engine is None when it could
        not be started, and problem then tells why.
    """
    if _runs_with(running, engine_settings) and running.process is not None:
        return running.process, False, ""
    engine, _, problem = start_engine(engine_settings)
    return engine, True, problem


def measure_katago_speed(engine_settings: EngineSettings, running: Engines | None = None) -> MeasuredSpeed:
    """Measure the speed of the model.

    When the app's KataGo runs with these settings, it is measured as it is: loaded, as the screens
    use it. Otherwise a KataGo of its own is started, and stopped after measuring (see katago.speed).

    Args:
        engine_settings: The engine settings (saved in the settings file).
        running: The app's KataGo, or None.

    Raises:
        RuntimeError: If KataGo cannot be started (the message tells why).
        ValueError, TimeoutError: If KataGo does not answer well.
    """
    if _runs_with(running, engine_settings):
        return MeasuredSpeed(_measure_engine(running.engine))
    process, _, problem = start_engine(engine_settings)
    if process is None:
        raise RuntimeError(problem)
    try:
        return MeasuredSpeed(_measure_engine(process))
    finally:
        process.close()


def _runs_with(running: Engines | None, engine_settings: EngineSettings) -> bool:
    """True if the app's KataGo runs with the command line of the settings."""
    return (
        running is not None
        and running.engine is not None
        and running.command == engine_command_line(engine_settings, turned_off=False)
    )


def _measure_engine(engine: AnalysisEngine) -> float:
    """Measure the speed of a running KataGo, and write it to the console."""
    speed = measure_speed(lambda query: wait_for_answer(engine, query))
    print(f"KataGo speed: {speed:.0f} visits per second", file=sys.stderr)
    return speed
