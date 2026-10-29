"""Tests for kentogo.commentary.workspace."""

from commentary_samples import analyzed_game

from kentogo.commentary.commentary_settings import CommentarySettings
from kentogo.commentary.prompt_text import default_prompt_text
from kentogo.commentary.workspace import CommentaryWorkspace
from kentogo.mistakes.extract import ExtractSettings


def workspace(tmp_path):
    """Make a workspace with its files in tmp_path, and the default settings."""
    return CommentaryWorkspace(tmp_path / "settings.json", CommentarySettings, ExtractSettings)


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
