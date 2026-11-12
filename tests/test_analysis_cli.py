"""Tests for kentogo.analysis_cli (the command line of the analysis of games)."""

import json

import pytest
from pysgf import GoGame

from kentogo import analysis_cli
from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.record.kentogo_analysis import read_kentogo_analysis
from kentogo.settings_file import load_settings

GAME = "(;SZ[5]KM[0.5];B[cc];W[bb])"


class FakeEngine:
    """A started KataGo that answers at once."""

    def __init__(self):
        self.closed = False

    def wait_until_ready(self, timeout):
        return True

    def query(self, request, callback):
        allowed = request.get("allowMoves")
        point = allowed[0]["moves"][0] if allowed else "E5"
        score = float(len(request["moves"]) + (1 if allowed else 0))
        root = {"scoreLead": score, "winrate": 0.5, "visits": request["maxVisits"]}
        best = {**root, "move": point, "order": 0, "pv": [point]}
        callback({"id": "q", "rootInfo": root, "moveInfos": [best]})
        return "q"

    def close(self):
        self.closed = True


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A games folder with one game, a settings file that names it, and the fake KataGo."""
    games = tmp_path / "games"
    games.mkdir()
    (games / "game.sgf").write_text(GAME, encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"analysis": {"games_folder": str(games)}}), encoding="utf-8")
    engine = FakeEngine()
    monkeypatch.setattr(analysis_cli, "start_engine", lambda _settings: (engine, None, ""))
    # Without KaTrain's settings of this computer.
    monkeypatch.setattr(analysis_cli, "load_settings", lambda path: load_settings(path, tmp_path / "none.json"))
    return games, settings, engine


def test_options_replace_the_settings():
    arguments = analysis_cli.parse_arguments(["--backup", "/b"])
    assert analysis_cli.settings_with_options(AnalysisSettings(), arguments).backup_folder == "/b"
    unchanged = analysis_cli.settings_with_options(AnalysisSettings(fast_visits=99), analysis_cli.parse_arguments([]))
    assert unchanged == AnalysisSettings(fast_visits=99)
    with pytest.raises(ValueError):
        analysis_cli.settings_with_options(AnalysisSettings(fast_visits=0), analysis_cli.parse_arguments([]))
    with pytest.raises(SystemExit):  # The options of the analysis again are gone.
        analysis_cli.parse_arguments(["--reanalyze"])


def test_analyze_the_games_folder(folder, capsys):
    games, settings, engine = folder
    assert analysis_cli.main(["--settings", str(settings)]) == 0
    root = GoGame.parse_sgf((games / "game.sgf").read_text(encoding="utf-8"))
    assert all(read_kentogo_analysis(node)["completed"] for node in root.nodes_in_tree)
    assert [path.read_text(encoding="utf-8") for path in (games / "backup").iterdir()] == [GAME]
    assert engine.closed
    output = capsys.readouterr().out
    assert "[1/1] game.sgf" in output and "analysis: 3/3 nodes" in output


def test_an_analyzed_game_is_skipped_and_the_dry_run_changes_nothing(folder, capsys):
    games, settings, _ = folder
    analysis_cli.main(["--settings", str(settings)])
    written = (games / "game.sgf").read_text(encoding="utf-8")
    assert analysis_cli.main(["--settings", str(settings), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "3 nodes, 3 with analysis data -> skip (analyzed)" in output
    assert "loss B 1.5+, W 1.5+): 0 moves: none (file now" in output  # Half of 3 points: none lost it.
    assert analysis_cli.main(["--settings", str(settings)]) == 0
    assert "skipped" in capsys.readouterr().out
    assert (games / "game.sgf").read_text(encoding="utf-8") == written


def as_analyzed_by_katrain(path):
    """Remove KGM[KentoGo] from a written game, as if KaTrain had analyzed it."""
    path.write_text(path.read_text(encoding="utf-8").replace("KGM[KentoGo]", ""), encoding="utf-8")


def test_games_analyzed_by_katrain_are_asked_about(folder, capsys, monkeypatch):
    """A game analyzed by KaTrain is analyzed again for KentoGo only when the answer is y."""
    games, settings, _ = folder
    analysis_cli.main(["--settings", str(settings)])
    as_analyzed_by_katrain(games / "game.sgf")
    written = (games / "game.sgf").read_text(encoding="utf-8")
    assert analysis_cli.main(["--settings", str(settings), "--dry-run"]) == 0
    assert "ask (analyzed by KaTrain" in capsys.readouterr().out
    questions = []
    monkeypatch.setattr("builtins.input", lambda question: questions.append(question) or "n")
    assert analysis_cli.main(["--settings", str(settings)]) == 0
    assert (games / "game.sgf").read_text(encoding="utf-8") == written
    assert questions == [analysis_cli.KENTOGO_QUESTION.format(count=1)]
    monkeypatch.setattr("builtins.input", lambda question: "y")
    assert analysis_cli.main(["--settings", str(settings)]) == 0
    assert "KGM[KentoGo]" in (games / "game.sgf").read_text(encoding="utf-8")
    questions.clear()
    monkeypatch.setattr("builtins.input", lambda question: questions.append(question) or "y")
    analysis_cli.main(["--settings", str(settings)])  # Analyzed by KentoGo: not asked.
    assert questions == []


def test_there_is_no_option_of_katrains_way():
    """KaTrain's own way of analysis is not offered: KaTrain itself can analyze a game that needs it."""
    for option in ("--compatible", "--improved"):
        with pytest.raises(SystemExit):
            analysis_cli.parse_arguments([option])


def test_the_question_waits_for_y_or_n():
    answers = iter(["", "maybe", "Y"])
    assert analysis_cli.ask_kentogo_redo(2, lambda question: next(answers)) is True

    def no_console(question):
        raise EOFError

    assert analysis_cli.ask_kentogo_redo(2, no_console) is False
