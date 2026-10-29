"""Tests for kentogo.record.library."""

import os

from kentogo.record.ai_comment import AI_HEADER, REVIEW_HEADER
from kentogo.record.library import games_with_ai, list_games


def write(folder, name, text, modified_ns):
    """Write a file with a time of change."""
    path = folder / name
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(modified_ns, modified_ns))
    return path


def test_newest_first_with_ai_marks(tmp_path):
    """The games are listed from the newest, and the games with an AI commentary or review are found."""
    write(tmp_path, "old.sgf", f"(;SZ[9];B[aa]C[{AI_HEADER}\nx])", 1_000)
    write(tmp_path, "new.sgf", "(;SZ[9];B[aa])", 3_000)
    write(tmp_path, "review.sgf", f"(;SZ[9];B[aa]C[{REVIEW_HEADER}\ny])", 2_000)
    write(tmp_path, "notes.txt", "not a game", 4_000)
    games = list_games(tmp_path)
    assert [(game.name, game.has_ai) for game in games] == [("new.sgf", False), ("review.sgf", True), ("old.sgf", True)]
    assert [game.name for game in games_with_ai(games)] == ["review.sgf", "old.sgf"]
    assert list_games(tmp_path / "missing") == []


def test_english_headers_are_ai_marks(tmp_path):
    """A commentary or a review with the English headers is found too."""
    from kentogo.record.ai_comment import AI_HEADER_EN, REVIEW_HEADER_EN

    write(tmp_path, "move.sgf", f"(;SZ[9];B[aa]C[{AI_HEADER_EN}\nx])", 1_000)
    write(tmp_path, "review.sgf", f"(;SZ[9];B[aa]C[{REVIEW_HEADER_EN}\ny])", 2_000)
    assert [game.has_ai for game in list_games(tmp_path)] == [True, True]
