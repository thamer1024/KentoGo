"""Tests for kentogo.opponent_rank (the ranks of the players, for the human-like moves of KataGo's sequences)."""

from kentogo.commentary.history import CommentaryHistory, history_path
from kentogo.opponent_rank import given_rank, player_ranks
from kentogo.quiz.human_line import PlayerRanks


def game(tmp_path, ranks: str) -> str:
    """Write a game with the rank properties, and return its path."""
    path = tmp_path / "game.sgf"
    path.write_text(f"(;SZ[19]{ranks};B[pd])", encoding="utf-8")
    return str(path)


def test_ranks_from_the_file(tmp_path):
    """The user (white) has the rank in the file, else the given one; the opponent its own, else the user's."""
    given = {"game.sgf": "12k"}.get
    assert player_ranks(game(tmp_path, "BR[10級]"), "W", lambda name: given(name, "")) == PlayerRanks("12k", "10k")
    assert player_ranks(game(tmp_path, "BR[3d]WR[5k]"), "W", lambda name: given(name, "")) == PlayerRanks("5k", "3d")
    assert player_ranks(game(tmp_path, "WR[5k]"), "W", lambda name: given(name, "")) == PlayerRanks("5k", "5k")
    assert player_ranks(game(tmp_path, ""), "W", lambda name: given(name, "")) == PlayerRanks("12k", "12k")
    assert player_ranks(str(tmp_path / "gone.sgf"), "W", lambda name: "") == PlayerRanks()


def test_the_rank_given_for_the_ai_commentary(tmp_path):
    """The rank given for the game, else the last rank given; without the history, none (and none is made)."""
    settings = tmp_path / "settings.json"
    assert given_rank(settings, "a.sgf") == "" and not history_path(settings).exists()
    history = CommentaryHistory(history_path(settings))
    history.save_inputs("a.sgf", "B", "8k", "same")
    history.save_inputs("b.sgf", "B", "", "same")
    history.close()
    assert (given_rank(settings, "a.sgf"), given_rank(settings, "b.sgf")) == ("8k", "8k")
