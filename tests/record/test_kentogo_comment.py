"""Tests for kentogo.record.kentogo_comment (KentoGo's own text in a comment)."""

from pysgf import GoGame

from kentogo.record.game_record import read_game_record
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR, read_comment
from kentogo.record.kentogo_comment import KENTOGO_HEADER, kentogo_part, split_kentogo_comment

KATRAIN = f"\nMove 1: B C3\nScore: B+1.0\n{INTERNAL_MARKER}"
KENTOGO = kentogo_part("損失: 3.0目\n最善手: D4")


def test_kentogos_part_is_taken_out():
    """The notes and KaTrain's text stay as they were; KentoGo's text comes without its header."""
    comment = f"my note\n{SEPARATOR}{KATRAIN}{SEPARATOR}\n{KENTOGO}"
    split = split_kentogo_comment(comment)
    assert split.text == "損失: 3.0目\n最善手: D4"
    notes, _ = read_comment(split.rest)
    assert notes == "my note" and KENTOGO_HEADER not in split.rest and "Move 1" in split.rest


def test_a_comment_without_kentogos_part_is_unchanged():
    comment = f"my note\n{SEPARATOR}{KATRAIN}"
    assert split_kentogo_comment(comment) == split_kentogo_comment(comment).__class__("", comment)


def test_the_game_record_reads_the_notes_without_kentogos_old_text():
    """The text that older versions of KentoGo wrote is not part of the notes."""
    root = GoGame.parse_sgf(f"(;SZ[9];B[cc]C[my note\n{SEPARATOR}\n{KENTOGO}])")
    assert read_game_record(root).moves[0].notes == "my note"
