"""KataGo for the app: start the main model and the comparison model, and measure their speed.

KataGo is started with the app, as in KaTrain (the main model first, then the comparison
model when the main one is ready, see katago.on_demand), and closed when the app closes. It is
started again only when the settings change its command line (see engines_for): new numbers of
visits use the running processes. The two KataGo processes get one query at a time between them
(see katago.one_at_a_time), so that they do not share the GPU.

The screens get the processes as Engines; they never start KataGo themselves.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, replace

from kentogo.katago.engine_settings import JUDGE_COMPARE, EngineSettings
from kentogo.katago.evaluate import AnalysisEngine, EvaluationSettings, Models
from kentogo.katago.locate import EngineCommand, KataGoNotFoundError, engine_command, fixed_settings, katrain_package
from kentogo.katago.on_demand import OnDemandEngine, start_after_ready
from kentogo.katago.one_at_a_time import OneAtATime, QueryLine
from kentogo.katago.process import KataGoProcess
from kentogo.katago.queries import FORCED_SETTINGS
from kentogo.katago.speed import MeasuredSpeed, measure_speed, wait_for_answer
from kentogo.katago.startup import LoadingStage
from kentogo.notice import Notice
from kentogo.quiz.quiz_run import Judging

# The cache of the comparison model's KataGo: 2 ** 18 results, at most about 0.4 to 0.8 GB (KaTrain's
# settings file has 2 ** 20, up to about 1.5 to 3 GB). It reads few positions, so it hardly gets slower.
COMPARE_CACHE = {"nnCacheSizePowerOfTwo": 18}


def evaluation_settings(engine_settings: EngineSettings, max_visits: int) -> EvaluationSettings:
    """Return how a model analyzes: its own number of visits, and the noise and the visits of 地と形勢 of the settings."""
    return EvaluationSettings(max_visits, engine_settings.wide_root_noise, engine_settings.estimate_visits)


def make_command(
    engine_settings: EngineSettings, engine: dict | None = None
) -> tuple[EngineCommand | None, EvaluationSettings, str]:
    """Make the command that starts KataGo, checking that its files exist.

    Args:
        engine_settings: The engine settings.
        engine: The engine in the form of KaTrain's settings, for another model
            (see EngineSettings.compare_engine). If None, the main model is used.

    Returns:
        A tuple (command, settings, problem). command is None if a file is missing, and
        problem then tells why. settings has the number of visits and the noise.
    """
    settings = evaluation_settings(engine_settings, engine_settings.max_visits)
    try:
        package = katrain_package(engine_settings.katrain_folder)
        command = engine_command(engine or engine_settings.katrain_engine(), package)
    except KataGoNotFoundError as error:
        return None, settings, str(error)
    if engine is not None:
        # The comparison model is often used with the settings file of the human-like model,
        # whose humanSLProfile would make every query fail (see locate.fixed_settings).
        # Its KataGo also gets a smaller cache (COMPARE_CACHE), as it runs beside the main one.
        command = fixed_settings(command, {**_query_settings(settings), **COMPARE_CACHE})
    return command, settings, ""


def start_engine(
    engine_settings: EngineSettings, engine: dict | None = None
) -> tuple[KataGoProcess | None, EvaluationSettings, str]:
    """Start KataGo with the engine settings.

    Args:
        engine_settings: The engine settings.
        engine: The engine in the form of KaTrain's settings, to start another model
            (see EngineSettings.compare_engine). If None, the main model is started.

    Returns:
        A tuple (engine, settings, problem). engine is None if KataGo could not be
        started, and problem then tells why. settings has the number of visits and the noise.
    """
    command, settings, problem = make_command(engine_settings, engine)
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


def _compare_engine(engine_settings: EngineSettings) -> tuple[OnDemandEngine | None, str]:
    """Prepare the KataGo with the comparison model.

    It is started when the main KataGo is ready (see open_engines), or by its first query
    if that comes first, and it runs until the app ends.

    Returns:
        A tuple (engine, problem). engine is None if it cannot be used, and problem tells why.
    """
    command, _, problem = make_command(engine_settings, engine_settings.compare_engine())
    print(problem or "KataGo with the comparison model is started after the main one", file=sys.stderr)
    return (OnDemandEngine(command) if command is not None else None), problem


def _query_settings(settings: EvaluationSettings) -> dict:
    """Return the settings that every query sends in "overrideSettings" (see katago.queries.position_query)."""
    values = dict(FORCED_SETTINGS)
    if settings.wide_root_noise is not None:
        values["wideRootNoise"] = settings.wide_root_noise
    return values


def start_engines(
    engine_settings: EngineSettings, turned_off: bool, notices: list[Notice] | None = None
) -> tuple[KataGoProcess | None, OnDemandEngine | None, EvaluationSettings, str]:
    """Start the main KataGo and, if it is turned on, the KataGo with the comparison model.

    Args:
        engine_settings: The engine settings.
        turned_off: True if KataGo is turned off for this start (--no-katago).
        notices: If given, messages for the user are added when a KataGo cannot be started
            (shown in a dialog, because the user does not look at the console).

    Returns:
        A tuple (engine, compare, settings, problem). engine and compare are None when they
        could not be started (problem tells why the main one could not).
    """
    if turned_off or not engine_settings.use_katago:
        return None, None, EvaluationSettings(), "KataGo is turned off"
    found = [] if notices is None else notices
    engine, evaluation, problem = start_engine(engine_settings)
    print(problem or f"KataGo started ({evaluation.max_visits} visits)", file=sys.stderr)
    if problem:
        found.append(Notice("notice_katago_failed", {"reason": problem}))
    compare = None
    if engine_settings.compare_on:
        compare, compare_problem = _compare_engine(engine_settings)
        if compare_problem:
            found.append(Notice("notice_compare_failed", {"reason": compare_problem}))
    if engine_settings.judge_model == JUDGE_COMPARE and compare is None:
        print("the comparison model is not running, so the main model calculates the losses", file=sys.stderr)
        found.append(Notice("notice_judge_fallback"))
    return engine, compare, evaluation, problem


@dataclass(frozen=True)
class Engines:
    """The KataGo processes of the app, started with the app and closed when it ends (as in KaTrain).

    The quiz and the screen that shows the games use them. They are started again only when
    their command lines change (another program, model or settings file); a change of the
    numbers of visits uses the running processes (see engines_for).

    Attributes:
        engine: KataGo (one query at a time), or None if it is not available.
        evaluation: How KataGo analyzes the positions.
        engine_problem: Why KataGo is not available ("" if it is available).
        compare_engine: KataGo with the comparison model (one query at a time), or None.
        judge_with_compare: True to calculate the losses with the comparison model.
        compare_evaluation: How the comparison model analyzes the positions (its own number of visits).
        notices: Problems found when they were started, to show the user.
        processes: The processes themselves (main, comparison), to close them.
        commands: The command lines they were started with (see engine_commands).
        compare_start: The thread that starts the comparison model when the main one is ready, or None.
    """

    engine: AnalysisEngine | None
    evaluation: EvaluationSettings
    engine_problem: str
    compare_engine: AnalysisEngine | None = None
    judge_with_compare: bool = False
    compare_evaluation: EvaluationSettings = EvaluationSettings()
    notices: tuple[Notice, ...] = ()
    processes: tuple = ()
    commands: tuple = (None, None)
    compare_start: threading.Thread | None = None

    def close(self) -> None:
        """Stop the KataGo processes."""
        for process in self.processes:
            if process is not None:
                process.close()

    def loading_stages(self) -> list[LoadingStage]:
        """Return the KataGo processes to wait for at the start: the main one, then the comparison model's."""
        main, compare = self.processes
        if main is None:
            return []
        if compare is None:
            return [_main_stage(main)]
        return [_main_stage(main), _compare_stage(compare, self.compare_start)]

    def judging(self) -> Judging:
        """Return KataGo for the quiz: for judging the answers and showing sequences."""
        return Judging(
            self.engine,
            self.evaluation,
            self.engine_problem,
            self.compare_engine,
            self.compare_evaluation,
            self.judge_with_compare,
        )

    def viewer_models(self) -> Models:
        """Return the models for the screen that shows the games (those that are running)."""
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


def _compare_stage(compare: OnDemandEngine, starting: threading.Thread | None) -> LoadingStage:
    """Return the loading of the comparison model's KataGo, which a thread starts when the main one is ready.

    It has failed when it does not run and the thread that starts it has ended.
    """
    return LoadingStage(
        "loading_compare",
        " ".join(compare.command.command),
        lambda: compare.wait_until_ready(0),
        lambda: not compare.is_running and (starting is None or not starting.is_alive()),
        lambda: compare.ready_seconds,
    )


def open_engines(engine_settings: EngineSettings, turned_off: bool) -> Engines:
    """Start KataGo for the app (see start_engines). Problems are told in the notices.

    Both KataGo processes get one query at a time, so that they do not share the GPU (see one_at_a_time).
    The comparison model's KataGo is started when the main one is ready, so that the two do not
    load at the same time (see on_demand.start_after_ready).
    """
    notices: list[Notice] = []
    commands = engine_commands(engine_settings, turned_off)
    engine, compare, evaluation, problem = start_engines(engine_settings, turned_off, notices)
    compare_start = start_after_ready(engine, compare) if engine is not None and compare is not None else None
    line = QueryLine()
    return Engines(
        OneAtATime(engine, line) if engine is not None else None,
        evaluation,
        problem,
        OneAtATime(compare, line) if compare is not None else None,
        engine_settings.judge_model == JUDGE_COMPARE,
        evaluation_settings(engine_settings, engine_settings.compare_max_visits),
        tuple(notices),
        (engine, compare),
        commands,
        compare_start,
    )


def engine_commands(engine_settings: EngineSettings, turned_off: bool) -> tuple:
    """Return the command lines of the main KataGo and of the comparison model's (None for one that is not used).

    A command line is the program with its arguments, and whether the shell runs it: not the
    number of visits, which each query sends.
    """
    if turned_off or not engine_settings.use_katago:
        return None, None
    main, _, _ = make_command(engine_settings)
    compare = None
    if engine_settings.compare_on:
        compare, _, _ = make_command(engine_settings, engine_settings.compare_engine())
    return _command_line(main), _command_line(compare)


def _command_line(command: EngineCommand | None) -> tuple | None:
    """Return what starts KataGo in a command (see engine_commands), or None for None."""
    return None if command is None else (command.command, command.shell)


def engines_for(running: Engines | None, engine_settings: EngineSettings, turned_off: bool) -> Engines:
    """Return KataGo for some settings: the running processes if they fit them, or new ones.

    The running processes are kept when they were started with the same command lines: only the
    numbers of visits, the noise and the model that judges change. Otherwise they are closed, and
    new ones are started.

    Args:
        running: The KataGo processes that run now, or None.
        engine_settings: The engine settings.
        turned_off: True if KataGo is turned off for this start (--no-katago).
    """
    if running is not None and running.commands == engine_commands(engine_settings, turned_off):
        return replace(
            running,
            evaluation=evaluation_settings(engine_settings, engine_settings.max_visits),
            judge_with_compare=engine_settings.judge_model == JUDGE_COMPARE and running.compare_engine is not None,
            compare_evaluation=evaluation_settings(engine_settings, engine_settings.compare_max_visits),
            notices=(),
        )
    if running is not None:
        running.close()
    return open_engines(engine_settings, turned_off)


def measure_katago_speed(engine_settings: EngineSettings, running: Engines | None = None) -> MeasuredSpeed:
    """Measure the speed of the main model, and of the comparison model when it is turned on.

    When the app's KataGo runs with these settings, it is measured as it is: loaded, as the screens
    use it. Otherwise each model gets a KataGo of its own, one after the other, which is stopped
    after measuring (see katago.speed). The models can be very different in speed, so each one is
    measured; a comparison model that is the same file as the main model is not measured again.

    Args:
        engine_settings: The engine settings (saved in the settings file).
        running: The app's KataGo, or None.

    Raises:
        RuntimeError: If KataGo cannot be started (the message tells why).
        ValueError, TimeoutError: If KataGo does not answer well.
    """
    loaded = running if _runs_with(running, engine_settings) else None
    main = _measure_model(engine_settings, loaded, None)
    if not engine_settings.compare_on:
        return MeasuredSpeed(main)
    if not engine_settings.models_differ:
        return MeasuredSpeed(main, main)  # The same model reads at the same speed.
    return MeasuredSpeed(main, _measure_model(engine_settings, loaded, engine_settings.compare_engine()))


def _runs_with(running: Engines | None, engine_settings: EngineSettings) -> bool:
    """True if the app's KataGo runs with the command lines of the settings."""
    return (
        running is not None
        and running.engine is not None
        and running.commands == engine_commands(engine_settings, turned_off=False)
    )


def _measure_model(engine_settings: EngineSettings, running: Engines | None, engine: dict | None) -> float:
    """Measure a model (the main one for None): with the app's KataGo when it is given, or else with a new one."""
    name = "main" if engine is None else "comparison"
    if running is not None:
        return _measure_engine(running.engine if engine is None else running.compare_engine, name)
    return _measure_new_katago(engine_settings, engine, name)


def _measure_new_katago(engine_settings: EngineSettings, engine: dict | None, name: str) -> float:
    """Start a KataGo with a model (the main one for None, see start_engine), measure its speed, and stop it."""
    process, _, problem = start_engine(engine_settings, engine)
    if process is None:
        raise RuntimeError(problem)
    try:
        return _measure_engine(process, name)
    finally:
        process.close()


def _measure_engine(engine: AnalysisEngine, name: str) -> float:
    """Measure the speed of a running KataGo, and write it to the console ("main" or "comparison" model)."""
    speed = measure_speed(lambda query: wait_for_answer(engine, query))
    print(f"KataGo speed: {speed:.0f} visits per second ({name} model)", file=sys.stderr)
    return speed
