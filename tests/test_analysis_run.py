"""Tests for kentogo.analysis_run (analyzing the games of a folder, for the command line and the settings screen)."""

import threading
from pathlib import Path

from kentogo import analysis_run, engines
from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.analyze import DeepTargets
from kentogo.analysis_run import (
    FAILED,
    GAME_BROKEN,
    GAME_KATRAIN,
    GAME_KENTOGO,
    GAME_NEW,
    SKIPPED,
    WRITTEN,
    AnalysisListener,
    FolderGame,
    FolderGames,
    GameChoice,
    analyze_chosen_games,
    analyze_games,
    list_games,
    run_analysis,
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


def test_run_analysis_with_a_katago_of_its_own(tmp_path, monkeypatch):
    """Without the app's KataGo, one is started for the run and stopped after it."""
    folder = games(tmp_path)
    engine = FakeEngine()
    monkeypatch.setattr(analysis_run, "analysis_engine", lambda settings, running: (engine, True, ""))
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    summary = run_analysis(settings, None, [folder / "a.sgf"], Recorder().listener())
    assert summary.outcomes[WRITTEN] == 1 and engine.closed


def test_run_analysis_problems(tmp_path, monkeypatch):
    assert run_analysis(AppSettings(), None, [], Recorder().listener()).problem == "no games chosen"
    folder = games(tmp_path)
    monkeypatch.setattr(analysis_run, "analysis_engine", lambda settings, running: (None, True, "no KataGo"))
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    assert run_analysis(settings, None, [folder / "a.sgf"], Recorder().listener()).problem == "no KataGo"


def test_analysis_engine_starts_one_without_the_app(monkeypatch):
    started = FakeEngine()
    monkeypatch.setattr(engines, "start_engine", lambda settings: (started, None, ""))
    assert engines.analysis_engine(EngineSettings(), None) == (started, True, "")


def test_list_games_tells_what_each_game_is(tmp_path):
    folder = games(tmp_path)
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    assert list_games(settings).games == (
        FolderGame(folder / "a.sgf", GAME_NEW),
        FolderGame(folder / "b.sgf", GAME_BROKEN),
    )
    analyze_games(FakeEngine(), [folder / "a.sgf"], settings, Recorder().listener())  # a.sgf is analyzed now.
    listed = list_games(settings)
    assert (listed.folder, listed.backup) == (folder, folder / "backup")
    assert [game.state for game in listed.games] == [GAME_KENTOGO, GAME_BROKEN]
    assert listed.without_kentogo == (FolderGame(folder / "b.sgf", GAME_BROKEN),) and listed.kentogo_count == 1
    assert list_games(AppSettings(analysis=AnalysisSettings(games_folder=str(tmp_path / "x")))).games == ()
    assert list_games(AppSettings()).folder is None


def test_games_analyzed_by_katrain_are_analyzed_again_for_kentogo_when_asked(tmp_path):
    folder = games(tmp_path)
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    game = folder / "a.sgf"
    analyze_games(FakeEngine(), [game], settings, Recorder().listener())
    game.write_text(game.read_text(encoding="utf-8").replace("KGM[KentoGo]", ""), encoding="utf-8")  # As KaTrain.
    assert analysis_run.game_state(game) == GAME_KATRAIN
    skipped = analyze_games(FakeEngine(), [game], settings, Recorder().listener())
    assert skipped.outcomes[SKIPPED] == 1
    redone = analyze_games(FakeEngine(), [game], settings, Recorder().listener(), redo_kentogo=True)
    assert redone.outcomes[WRITTEN] == 1 and "KGM[KentoGo]" in game.read_text(encoding="utf-8")
    assert analysis_run.game_state(game) == GAME_KENTOGO  # Analyzed by KentoGo now.


def test_chosen_games_are_analyzed_even_when_they_are_analyzed(tmp_path):
    """A game that the user chose is never skipped; a file that cannot be read fails."""
    folder = games(tmp_path)
    settings = AppSettings(analysis=AnalysisSettings(games_folder=str(folder)))
    paths = analysis_run.find_games([folder])
    analyze_games(FakeEngine(), paths[:1], settings, Recorder().listener())
    summary = analyze_chosen_games(FakeEngine(), paths, settings, Recorder().listener())
    assert summary.outcomes == {WRITTEN: 1, SKIPPED: 0, FAILED: 1}


def test_a_chosen_run_stops_after_the_current_game(tmp_path):
    folder = games(tmp_path)
    stop = threading.Event()
    recorder = Recorder(stop)
    paths = analysis_run.find_games([folder])
    summary = analyze_chosen_games(FakeEngine(), paths, AppSettings(), recorder.listener(), stop)
    assert summary.stopped and [event[0] for event in recorder.events] == ["started", "finished"]


def test_only_the_games_not_analyzed_are_checked_first():
    """With "analyze again", the games analyzed by KaTrain are checked too; those analyzed by KentoGo never are."""
    plain, again = AnalysisSettings(), AnalysisSettings(reanalyze=True)
    for state, first, with_again in [
        (GAME_NEW, True, True),
        (GAME_BROKEN, True, True),
        (GAME_KATRAIN, False, True),
        (GAME_KENTOGO, False, False),
    ]:
        game = FolderGame(Path(f"{state}.sgf"), state)
        assert (game.checked_first(plain), game.checked_first(again)) == (first, with_again), state


def choice_of_four() -> tuple[GameChoice, list[FolderGame]]:
    """A choice of four games, one of each state, the games analyzed by KentoGo hidden."""
    four = [FolderGame(Path(f"{state}.sgf"), state) for state in (GAME_NEW, GAME_KATRAIN, GAME_KENTOGO, GAME_BROKEN)]
    return GameChoice(FolderGames(Path("games"), Path("backup"), tuple(four)), AnalysisSettings()), four


def test_the_games_analyzed_by_kentogo_are_listed_only_when_asked():
    choice, (new, katrain, kentogo, broken) = choice_of_four()
    assert choice.listed() == (new, katrain, broken)
    assert choice.chosen() == [new.path, broken.path]
    choice.with_kentogo = True
    assert choice.listed() == (new, katrain, kentogo, broken)
    assert choice.chosen() == [new.path, broken.path]  # Listed, but not checked.


def test_the_checks_are_kept_while_the_games_are_hidden():
    """A hidden game is not chosen, but its check is kept until it is shown again."""
    choice, (new, katrain, kentogo, broken) = choice_of_four()
    choice.with_kentogo = True
    choice.set_checked(kentogo, True)
    choice.set_checked(new, False)
    assert choice.chosen() == [kentogo.path, broken.path]
    choice.with_kentogo = False
    assert choice.chosen() == [broken.path] and choice.is_checked(kentogo)
    choice.with_kentogo = True
    assert choice.chosen() == [kentogo.path, broken.path]


def test_all_the_listed_games_are_checked_or_unchecked():
    choice, (new, katrain, kentogo, broken) = choice_of_four()
    choice.set_all_listed(True)
    assert choice.chosen() == [new.path, katrain.path, broken.path] and not choice.is_checked(kentogo)
    choice.with_kentogo = True
    choice.set_all_listed(False)
    assert choice.chosen() == []


def test_deep_targets_come_from_the_quiz_settings():
    """The user's moves from the smallest loss of a problem, the opponent's from the loss of a punishment chance."""
    from pysgf import GoGame

    from kentogo.mistakes.extract import ExtractSettings
    from kentogo.quiz.quiz_settings import QuizSettings

    extract = ExtractSettings(
        my_names=("hama",), min_points_lost=3.0, loss_stages=(20.0, 5.0), punish_opponent_loss=15.0
    )
    settings = AppSettings(quiz=QuizSettings(extract=extract), engine=EngineSettings(max_visits=500))
    root = GoGame.parse_sgf("(;SZ[9]PB[hama]PW[AI];B[ee])")
    targets = analysis_run.deep_targets(settings, root, Path("game.sgf"))
    assert (targets.losses, targets.visits, targets.my_colors) == (
        {"B": 5.0, "W": 15.0},
        500,
        {"B"},
    )  # The last stage; the engine's visits.
    unknown = GoGame.parse_sgf("(;SZ[9]PB[someone]PW[other];B[ee])")
    deep = AppSettings(quiz=QuizSettings(extract=extract), analysis=AnalysisSettings(deep_visits=3000))
    assert analysis_run.deep_targets(deep, unknown, Path("x.sgf")) == DeepTargets(
        {"B": 5.0, "W": 5.0}, 3000, max_moves=6, my_colors=frozenset({"B", "W"}), reply_loss=5.0
    )  # 6 moves of a game at most; an opponent's move when the reply lost 5 points (the quiz's punish_my_loss).
    assert targets.decided(0.995, 0.0) and targets.decided(0.5, -61.0) and not targets.decided(0.98, 10.0)
