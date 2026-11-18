"""Tests for kentogo.commentary.workspace."""

import threading
from datetime import datetime

import pytest
from commentary_samples import NOT_ANALYZED, analyzed_game, good_answer

from kentogo.commentary import workspace as workspace_module
from kentogo.commentary.batch import STATUS_DONE, BatchListener
from kentogo.commentary.commentary_settings import CommentarySettings
from kentogo.commentary.history import STATE_DONE, STATE_PENDING
from kentogo.commentary.job import GameRequest, NotAnalyzedError
from kentogo.commentary.language import JAPANESE
from kentogo.commentary.prompt_text import default_prompt_text
from kentogo.commentary.provider_base import ERROR_OTHER, Generation, ProviderError
from kentogo.commentary.since import SINCE_ALL, SINCE_DATE
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.mistakes.extract import ExtractSettings


def workspace(tmp_path):
    """Make a workspace with its files in tmp_path, and the default settings."""
    return CommentaryWorkspace(tmp_path / "settings.json", CommentarySettings, ExtractSettings)


class FakeProvider:
    """An AI that gives good answers."""

    def generate(self, _prompt, on_text, _cancel):
        answer = good_answer()
        on_text(answer[:5])
        return Generation(answer, 100, 50)


def entry_of(space, name):
    """Return what the history of a workspace remembers about a game."""
    history = space.open_history()
    try:
        return history.entry(name)
    finally:
        history.close()


def test_asking_about_one_game_writes_the_answer(games, tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_module, "make_provider", lambda _settings: FakeProvider())
    space = workspace(tmp_path)
    pieces = []
    request = GameRequest(games("a.sgf", analyzed_game()), "B", "18k", "same")
    outcome, problems = space.ask_game(request, JAPANESE, BatchListener(on_text=pieces.append), threading.Event())
    assert (outcome.status, problems) == (STATUS_DONE, []) and pieces
    assert entry_of(space, "a.sgf").state == STATE_DONE


def test_asking_tells_when_the_ai_cannot_be_used(games, tmp_path, monkeypatch):
    def no_provider(_settings):
        raise ProviderError(ERROR_OTHER, "no key")

    monkeypatch.setattr(workspace_module, "make_provider", no_provider)
    request = GameRequest(games("a.sgf", analyzed_game()), "B")
    with pytest.raises(ProviderError):
        workspace(tmp_path).ask_game(request, JAPANESE, BatchListener(), threading.Event())


def test_asking_about_listed_games_updates_the_list(games, tmp_path, monkeypatch):
    """The other games not analyzed become pending, and the time of the run is remembered."""
    monkeypatch.setattr(workspace_module, "make_provider", lambda _settings: FakeProvider())
    space = workspace(tmp_path)
    request = GameRequest(games("a.sgf", analyzed_game()), "B", "18k", "same")
    outcomes = space.ask_listed_games([request], ["raw.sgf"], JAPANESE, BatchListener(), threading.Event())
    assert [outcome.status for outcome in outcomes] == [STATUS_DONE]
    assert entry_of(space, "raw.sgf").state == STATE_PENDING
    assert space.games_to_list(games.folder) is not None


def test_the_list_of_games_asks_how_far_back_only_the_first_time(games, tmp_path):
    games("a.sgf", analyzed_game())
    space = workspace(tmp_path)
    assert space.games_to_list(games.folder) is None
    with pytest.raises(ValueError):
        space.choose_since(SINCE_DATE, "not a date", datetime(2026, 11, 1))
    assert space.games_to_list(games.folder) is None
    space.choose_since(SINCE_ALL, "", datetime(2026, 11, 1))
    assert [game.name for game in space.games_to_list(games.folder)] == ["a.sgf"]
    space.exclude_game("a.sgf")
    assert space.games_to_list(games.folder) == []


def test_the_list_works_without_a_history(games, tmp_path):
    games("a.sgf", analyzed_game())
    space = workspace(tmp_path)
    (tmp_path / "commentary_history.sqlite3").write_text("not a database")
    assert space.games_to_list(games.folder) == []
    space.choose_since(SINCE_ALL, "", datetime(2026, 11, 1))
    space.exclude_game("a.sgf")


def test_a_pasted_answer_is_written(games, tmp_path):
    space = workspace(tmp_path)
    request = GameRequest(games("a.sgf", analyzed_game()), "B", "18k", "same")
    prepared, problems = space.prepare_for_paste(request, JAPANESE)
    assert problems == []
    assert space.apply_pasted_answer(prepared, good_answer()).written is not None
    assert entry_of(space, "a.sgf").state == STATE_DONE


def test_a_game_not_analyzed_is_remembered_for_the_paste_mode(games, tmp_path):
    space = workspace(tmp_path)
    request = GameRequest(games("raw.sgf", NOT_ANALYZED), "B", "18k")
    with pytest.raises(NotAnalyzedError):
        space.prepare_for_paste(request, JAPANESE)
    assert entry_of(space, "raw.sgf").state == STATE_PENDING


def test_candidate_uses_the_last_rank(games, tmp_path):
    """A chosen game gets the last rank given for another game."""
    path = games("a.sgf", analyzed_game())
    space = workspace(tmp_path)
    history = space.open_history()
    history.save_inputs("other.sgf", "W", "15k", "")
    history.close()
    assert space.candidate(path).my_rank == "15k"


def test_prompt_text_and_broken_history(tmp_path):
    """The prompt file is read (the default without a file), and a broken history is not used."""
    space = workspace(tmp_path)
    assert space.prompt_text() == (default_prompt_text(), [])
    (tmp_path / "commentary_history.sqlite3").write_text("not a database")
    assert space.open_history() is None


def test_settings_from_the_file(tmp_path):
    """The settings of the AI commentary and the number of moves come from the settings as they are now."""
    space = workspace(tmp_path)
    assert space.commentary_settings().model == "claude-opus-5-5"
    assert space.conditions() == ExtractSettings()  # The quiz's conditions for choosing problems.
