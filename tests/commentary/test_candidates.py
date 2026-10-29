"""Tests for kentogo.commentary.candidates."""

from commentary_samples import HUMAN, NOT_ANALYZED, analyzed_game

from kentogo.commentary.candidates import candidate_for, guess_relation, is_shown, list_candidates
from kentogo.commentary.history import STATE_DONE, STATE_EXCLUDED, STATE_PENDING, CommentaryHistory, GameEntry
from kentogo.record.ai_comment import AI_HEADER


def test_which_games_are_shown():
    """Pending games, and games changed after the time, are shown; excluded and unchanged done games are not."""
    assert is_shown(GameEntry("a"), 2000, 1000) and not is_shown(GameEntry("a"), 1000, 1000)
    assert is_shown(GameEntry("a", state=STATE_PENDING), 10, 1000)
    assert not is_shown(GameEntry("a", state=STATE_EXCLUDED), 2000, 1000)
    assert not is_shown(GameEntry("a", state=STATE_DONE, done_modified_ns=2000), 2000, 1000)
    assert is_shown(GameEntry("a", state=STATE_DONE, done_modified_ns=1500), 2000, 1000)


def test_guess_relation():
    """An even game is against the same rank; without komi the weaker player takes black."""
    assert guess_relation(6.5, "W") == "same"
    assert (guess_relation(0.5, "B"), guess_relation(0.5, "W"), guess_relation(0.5, "")) == ("higher", "lower", "")
    assert guess_relation(3.5, "B") == ""


def test_list_with_first_values(games):
    """The list has the shown games, the oldest first, with the first values of the inputs."""
    games("new.sgf", analyzed_game(), 3_000)
    games("old.sgf", analyzed_game(komi=0.5), 2_000)
    games("before.sgf", analyzed_game(), 500)
    games("raw.sgf", NOT_ANALYZED, 2_500)
    games("fox.sgf", analyzed_game("Taro", "Opponent", extra="BR[3段]"), 2_600)
    history = CommentaryHistory(":memory:")
    found = list_candidates(games.folder, history, 1_000, my_names=["Taro"], default_rank="18k")
    assert [game.name for game in found] == ["old.sgf", "raw.sgf", "fox.sgf", "new.sgf"]
    old, raw, fox, new = found
    assert (old.my_color, old.my_rank, old.relation, old.analyzed, old.has_ai) == ("B", "18k", "higher", True, False)
    assert (raw.analyzed, raw.my_color) == (False, "B")
    assert (fox.my_color, fox.my_rank, fox.black_name) == ("B", "3d", "Taro")  # The rank in the game.
    assert new.final_state.stones[(4, 4)] == "B" and new.result == ""


def test_remembered_inputs_and_states(games):
    """Inputs given before are used, a pending game is shown even if old, and an AI commentary is noticed."""
    games("a.sgf", analyzed_game(HUMAN, HUMAN), 500)
    games("b.sgf", analyzed_game().replace(";B[ee]C[", f";B[ee]C[{AI_HEADER}\\nold\\n", 1), 2_000)
    history = CommentaryHistory(":memory:")
    history.save_inputs("a.sgf", "W", "15k", "lower")
    history.mark_pending("a.sgf")
    a, b = list_candidates(games.folder, history, 1_000)
    assert (a.pending, a.my_color, a.my_rank, a.relation) == (True, "W", "15k", "lower")
    assert b.has_ai and not b.pending


def test_unknown_color_and_broken_file(games):
    """A game between two humans has no color, and a broken file is shown with its error."""
    games("a.sgf", analyzed_game(HUMAN, HUMAN), 2_000)
    games("b.sgf", "not an sgf file", 2_000)
    a, b = list_candidates(games.folder, CommentaryHistory(":memory:"), 1_000)
    assert (a.my_color, a.analyzed) == ("", True)
    assert b.error != "" and b.final_state is None


def test_candidate_for_one_game(games, tmp_path):
    """One chosen game gets the same first values as in the list, also without the history."""
    path = games("a.sgf", analyzed_game(komi=0.5), 500)
    history = CommentaryHistory(":memory:")
    history.save_inputs("a.sgf", "", "16k", "")
    game = candidate_for(path, history, default_rank="18k")
    assert (game.my_color, game.my_rank, game.relation, game.analyzed) == ("B", "16k", "higher", True)
    assert candidate_for(path, None, default_rank="18k").my_rank == "18k"
    assert candidate_for(tmp_path / "missing.sgf", None).error != ""
