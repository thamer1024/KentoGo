"""Tests for kentogo.analysis_cli (the command line of the analysis of games)."""

import json

import pytest
from pysgf import GoGame

from kentogo import analysis_cli
from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.record.katrain_kt import decode_kt
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
    arguments = analysis_cli.parse_arguments(["--mistakes-only", "--from", "30", "--to", "150", "--backup", "/b"])
    settings = analysis_cli.settings_with_options(AnalysisSettings(), arguments)
    assert (settings.reanalyze, settings.mistakes_only, settings.move_from, settings.move_to) == (True, True, 30, 150)
    assert settings.backup_folder == "/b" and settings.katrain_compatible is True
    unchanged = analysis_cli.settings_with_options(AnalysisSettings(fast=True), analysis_cli.parse_arguments([]))
    assert unchanged == AnalysisSettings(fast=True)
    with pytest.raises(ValueError):
        analysis_cli.settings_with_options(AnalysisSettings(), analysis_cli.parse_arguments(["--from", "-1"]))


def test_analyze_the_games_folder(folder, capsys):
    games, settings, engine = folder
    assert analysis_cli.main(["--settings", str(settings)]) == 0
    root = GoGame.parse_sgf((games / "game.sgf").read_text(encoding="utf-8"))
    assert all(decode_kt(node.get_list_property("KT"))["completed"] for node in root.nodes_in_tree)
    assert [path.read_text(encoding="utf-8") for path in (games / "backup").iterdir()] == [GAME]
    assert engine.closed
    output = capsys.readouterr().out
    assert "[1/1] game.sgf" in output and "analysis: 3/3 nodes" in output


def test_an_analyzed_game_is_skipped_and_the_dry_run_changes_nothing(folder, capsys):
    games, settings, _ = folder
    analysis_cli.main(["--settings", str(settings)])
    written = (games / "game.sgf").read_text(encoding="utf-8")
    assert analysis_cli.main(["--settings", str(settings), "--dry-run"]) == 0
    assert "3 nodes, 3 with analysis data -> skip (analyzed)" in capsys.readouterr().out
    assert analysis_cli.main(["--settings", str(settings)]) == 0
    assert "skipped" in capsys.readouterr().out
    assert (games / "game.sgf").read_text(encoding="utf-8") == written


def test_the_mode_is_chosen_by_an_option(folder, capsys):
    _, settings, _ = folder
    assert analysis_cli.main(["--settings", str(settings), "--improved"]) == 0
    assert "Mode: KentoGo" in capsys.readouterr().out
    arguments = analysis_cli.parse_arguments(["--compatible"])
    assert analysis_cli.settings_with_options(AnalysisSettings(katrain_compatible=False), arguments).katrain_compatible


def test_kentogo_mode_asks_about_games_analyzed_in_katrains_way(folder, capsys, monkeypatch):
    """A game analyzed in KaTrain's way is analyzed again for KentoGo only when the answer is y."""
    games, settings, _ = folder
    analysis_cli.main(["--settings", str(settings)])  # KaTrain compatible: no KGM.
    written = (games / "game.sgf").read_text(encoding="utf-8")
    assert analysis_cli.main(["--settings", str(settings), "--improved", "--dry-run"]) == 0
    assert "ask (analyzed in KaTrain's way" in capsys.readouterr().out
    questions = []
    monkeypatch.setattr("builtins.input", lambda question: questions.append(question) or "n")
    assert analysis_cli.main(["--settings", str(settings), "--improved"]) == 0
    assert (games / "game.sgf").read_text(encoding="utf-8") == written
    assert questions == [analysis_cli.KENTOGO_QUESTION.format(count=1)]
    monkeypatch.setattr("builtins.input", lambda question: "y")
    assert analysis_cli.main(["--settings", str(settings), "--improved"]) == 0
    assert "KGM[KentoGo]" in (games / "game.sgf").read_text(encoding="utf-8")
    questions.clear()
    monkeypatch.setattr("builtins.input", lambda question: questions.append(question) or "y")
    analysis_cli.main(["--settings", str(settings), "--improved"])  # Analyzed in KentoGo's mode: not asked.
    assert questions == []


def test_the_question_waits_for_y_or_n():
    answers = iter(["", "maybe", "Y"])
    assert analysis_cli.ask_kentogo_redo(2, lambda question: next(answers)) is True

    def no_console(question):
        raise EOFError

    assert analysis_cli.ask_kentogo_redo(2, no_console) is False
