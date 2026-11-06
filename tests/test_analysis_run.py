"""Tests for kentogo.analysis_run (analyzing the games of a folder, for the command line and the settings screen)."""

import threading

from kentogo import analysis_run, engines
from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis_run import (
    FAILED,
    SKIPPED,
    WRITTEN,
    AnalysisListener,
    analyze_games,
    plan_analysis,
    run_folder_analysis,
)
from kentogo.app_settings import AppSettings
from kentogo.katago.engine_settings import EngineSettings

GAME = "(;SZ[5]KM[0.5];B[cc];W[bb])"


class FakeEngine:
    """A started KataGo that answers at once."""

    def __init__(self):
        self.closed = False
        self.queries = 0

    def wait_until_ready(self, timeout):
        return True

    def query(self, request, callback):
        self.queries += 1
        root = {"scoreLead": float(len(request["moves"])), "winrate": 0.5, "visits": request["maxVisits"]}
        callback({"id": "q", "rootInfo": root, "moveInfos": [{**root, "move": "E5", "order": 0, "pv": ["E5"]}]})
        return "q"

    def close(self):
        self.closed = True


class Recorder:
    """Keeps what the listener is told."""

    def __init__(self, stop: threading.Event | None = None):
        self.events = []
        self.stop = stop

    def listener(self) -> AnalysisListener:
        def finished(name, outcome, detail):
            self.events.append(("finished", name, outcome))
            if self.stop is not None:
                self.stop.set()  # Asked to stop during the first game.

        return AnalysisListener(
            lambda number, total, name: self.events.append(("started", number, total, name)),
            lambda step, done, total: None,
            finished,
        )


def games(tmp_path):
    """A folder with a game, a broken file and a game written by the analysis before."""
    folder = tmp_path / "games"
    folder.mkdir()
    (folder / "a.sgf").write_text(GAME, encoding="utf-8")
    (folder / "b.sgf").write_text("not an SGF", encoding="utf-8")
    return folder


def test_each_game_is_written_skipped_or_failed(tmp_path):
    folder = games(tmp_path)
    settings = AppSettings()
    paths = analysis_run.find_games([folder])
    recorder = Recorder()
    summary = analyze_games(FakeEngine(), paths, settings, recorder.listener())
    assert summary.outcomes == {WRITTEN: 1, SKIPPED: 0, FAILED: 1}
    assert recorder.events[0] == ("started", 1, 2, "a.sgf")
    again = analyze_games(FakeEngine(), paths[:1], settings, Recorder().listener())  # a.sgf has its data now.
    assert again.outcomes[SKIPPED] == 1
    assert (folder / "backup").is_dir()


def test_a_run_stops_after_the_current_game(tmp_path):
    folder = games(tmp_path)
    stop = threading.Event()
    recorder = Recorder(stop)
    summary = analyze_games(FakeEngine(), analysis_run.find_games([folder]), AppSettings(), recorder.listener(), stop)
    assert summary.stopped and [event[0] for event in recorder.events] == ["started", "finished"]


def test_run_folder_analysis_with_a_katago_of_its_own(tmp_path, monkeypatch):
    """Without the app's KataGo, one is started for the run and stopped after it."""
    folder = games(tmp_path)
    engine = FakeEngine()
    monkeypatch.setattr(analysis_run, "analysis_engine", lambda settings, running: (engine, True, ""))
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    summary = run_folder_analysis(settings, None, Recorder().listener())
    assert summary.outcomes[WRITTEN] == 1 and engine.closed


def test_run_folder_analysis_problems(tmp_path, monkeypatch):
    assert run_folder_analysis(AppSettings(), None, Recorder().listener()).problem.startswith("no games")
    folder = games(tmp_path)
    monkeypatch.setattr(analysis_run, "analysis_engine", lambda settings, running: (None, True, "no KataGo"))
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    assert run_folder_analysis(settings, None, Recorder().listener()).problem == "no KataGo"


def test_analysis_engine_starts_one_without_the_app(monkeypatch):
    started = FakeEngine()
    monkeypatch.setattr(engines, "start_engine", lambda settings: (started, None, ""))
    assert engines.analysis_engine(EngineSettings(), None) == (started, True, "")


def test_plan_analysis_counts_the_games_to_analyze(tmp_path):
    folder = games(tmp_path)
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    analyze_games(FakeEngine(), [folder / "a.sgf"], settings, Recorder().listener())  # a.sgf is analyzed now.
    plan = plan_analysis(settings)
    assert (plan.folder, plan.backup, plan.games, plan.analyzed, plan.count()) == (
        folder,
        folder / "backup",
        2,
        1,
        1,
    )  # The broken b.sgf is counted with the games to analyze.
    again = plan_analysis(AppSettings(analysis=AnalysisSettings(games_folder=str(folder), reanalyze=True)))
    assert again.count() == 2
    assert plan_analysis(AppSettings(analysis=AnalysisSettings(games_folder=str(tmp_path / "x")))).games == 0


def test_games_analyzed_by_katrain_are_analyzed_again_for_kentogo_when_asked(tmp_path):
    folder = games(tmp_path)
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    game = folder / "a.sgf"
    analyze_games(FakeEngine(), [game], settings, Recorder().listener())
    game.write_text(game.read_text(encoding="utf-8").replace("KGM[KentoGo]", ""), encoding="utf-8")  # As KaTrain.
    plan = plan_analysis(settings)
    assert (plan.analyzed, plan.kentogo_redo, plan.count(), plan.count(True)) == (1, 1, 1, 2)
    again = AppSettings(analysis=AnalysisSettings(games_folder=str(folder), reanalyze=True))
    assert plan_analysis(again).kentogo_redo == 0  # Analyzed again anyway.
    skipped = analyze_games(FakeEngine(), [game], settings, Recorder().listener())
    assert skipped.outcomes[SKIPPED] == 1
    redone = analyze_games(FakeEngine(), [game], settings, Recorder().listener(), redo_kentogo=True)
    assert redone.outcomes[WRITTEN] == 1 and "KGM[KentoGo]" in game.read_text(encoding="utf-8")
    assert plan_analysis(settings).kentogo_redo == 0  # Analyzed by KentoGo now.
