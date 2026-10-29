"""Tests for kentogo.gui.viewer_model."""

from pathlib import Path

from pysgf import GoGame

from kentogo.gui.board_view import MARK_BEST
from kentogo.gui.texts import TEXTS
from kentogo.gui.viewer_model import board_view, comment_text, game_label, loss_text, position_text
from kentogo.record.ai_comment import AI_HEADER
from kentogo.record.game_record import read_game_record
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR
from kentogo.record.library import GameFile

KATRAIN = f"\nMove 2: W A1\nEstimated point loss: 5.0\nPredicted top move was C3 (B+1.0).\nPV: WC3\n{INTERNAL_MARKER}"
GAME = f"(;SZ[9]AB[ee];B[cc];W[ai]C[{AI_HEADER}\nToo far.\n{SEPARATOR}\nnote{SEPARATOR}{KATRAIN}];B[tt])"


def record():
    """Read GAME."""
    return read_game_record(GoGame.parse_sgf(GAME))


def test_board_view():
    """The board has the stones of the position, the last move, and KaTrain's best move."""
    view = board_view(record(), 2)
    assert view.stones == {(4, 4): "B", (2, 6): "B", (0, 0): "W"}
    assert view.last_move == (0, 0) and view.marks == {(2, 2): (MARK_BEST,)}
    assert board_view(record(), 0).last_move is None and board_view(record(), 0).marks == {}


def test_texts():
    """The position, the loss, and the commentary with the notes are written for the move."""
    game = record()
    assert position_text(game, 0) == "対局開始（全3手）"
    assert position_text(game, 2) == "2手目 / 全3手　白 A1"
    assert position_text(game, 3) == "3手目 / 全3手　黒 パス"
    assert loss_text(game, 2) == "損失 5.0目　最善 C3" and loss_text(game, 1) == ""
    assert comment_text(game, 2) == f"{TEXTS['ai_commentary']}\nToo far.\n\nnote"
    assert comment_text(game, 0) == ""


def test_game_label():
    """A game with an AI commentary is marked in the list."""
    assert game_label(GameFile(Path("a.sgf"), 0, True)) == "★ a.sgf"
    assert game_label(GameFile(Path("b.sgf"), 0, False)) == "b.sgf"


def test_review_is_shown_on_its_move():
    """The move that holds the review shows it, so that "next AI commentary" does not end at an empty text."""
    from kentogo.record.ai_comment import REVIEW_HEADER

    text = GAME.replace(";B[tt])", f";B[tt]C[{REVIEW_HEADER}\nGood game.])")
    game = read_game_record(GoGame.parse_sgf(text))
    assert comment_text(game, 3) == f"{TEXTS['ai_review']}\nGood game."


BRANCHED = f"(;SZ[9]AB[ee];B[cc](;W[ai]C[{KATRAIN}];B[bi];W[hh])(;W[dd];B[gc]))"


def branched():
    """Read BRANCHED: move 2 has KaTrain's sequence (C3) and a branch (D6, G7)."""
    return read_game_record(GoGame.parse_sgf(BRANCHED))


def test_variations_at_a_move():
    """KaTrain's predicted sequence comes first, then the other branches of the file."""
    from kentogo.gui.viewer_model import SOURCE_BRANCH, SOURCE_KATRAIN, variations_at

    found = variations_at(branched(), 2)
    assert [(v.source, [m.gtp() for m in v.moves]) for v in found] == [
        (SOURCE_KATRAIN, ["C3"]),
        (SOURCE_BRANCH, ["D6", "G7"]),
    ]
    assert variations_at(branched(), 0) == () and variations_at(branched(), 3) == ()


def test_moving_through_the_game_and_the_sequences():
    """Tab shows each sequence in place of the move, then the game again; the moves follow what is shown."""
    from kentogo.gui.viewer_model import Browse, next_variation, step_game

    game = branched()
    at_move = Browse(2)
    assert step_game(game, at_move, 1) == Browse(3)  # Space and → follow the game.
    assert next_variation(game, at_move) == Browse(2, 0, 1)  # The first move of KaTrain's sequence.
    assert next_variation(game, Browse(2, 0, 1)) == Browse(2, 1, 1)  # The branch of the file.
    assert next_variation(game, Browse(2, 1, 2)) == at_move  # Back to the game where they branch off.
    assert next_variation(game, Browse(3)) == Browse(3)  # No sequence at move 3.
    assert step_game(game, Browse(2, 1, 1), 1) == Browse(2, 1, 2)  # In a sequence, the moves follow it.
    assert step_game(game, Browse(2, 1, 2), 1) == Browse(2, 1, 2)  # Its end is as far as it goes.
    assert step_game(game, Browse(2, 1, 1), -1) == Browse(1)  # Before its first move: the game before move 2.


def test_sequence_on_the_board_and_in_the_text():
    """The sequence is played from the position before the move, numbered, with the game move marked."""
    from kentogo.gui.board_view import MARK_ACTUAL
    from kentogo.gui.viewer_model import Browse, browse_view, variation_text

    game = branched()
    view = browse_view(game, Browse(2, 1, 2))
    assert view.stones == {(4, 4): "B", (2, 6): "B", (3, 5): "W", (6, 6): "B"}
    assert view.numbers == {(3, 5): 1, (6, 6): 2}
    assert view.marks == {(0, 0): (MARK_ACTUAL,)}
    text = variation_text(game, Browse(2, 1, 1))
    assert "2手目の代わり：&bl;D6&br; G7" in text and TEXTS["source_sgf_branch"] in text
    assert variation_text(game, Browse(2)) == "この手の代わりの手順が 2 つあります（Tab：予想進行に切替）"
    assert variation_text(game, Browse(3)) == TEXTS["viewer_no_variations"]
    assert variation_text(game, Browse(0)) == ""


def test_the_comparison_models_sequence_comes_last():
    """The comparison model's sequence (added by the screen) comes after the others, with its own marks."""
    from kentogo.common.types import Move
    from kentogo.gui.board_view import MARK_ACTUAL, MARK_COMPARE
    from kentogo.gui.viewer_model import (
        SOURCE_COMPARE,
        Browse,
        browse_view,
        is_last_sequence,
        next_variation,
        step_game,
        variations_at,
    )
    from kentogo.mistakes.problem import Variation

    game = branched()
    line = Variation((Move.from_gtp("E3", "W"), Move.from_gtp("F3", "B")), SOURCE_COMPARE)
    added = {2: line}
    assert variations_at(game, 2, added)[-1] == line and len(variations_at(game, 2, added)) == 3
    assert is_last_sequence(game, Browse(2, 1, 1)) and not is_last_sequence(game, Browse(2, 1, 1), added)
    assert is_last_sequence(game, Browse(3)) and not is_last_sequence(game, Browse(2))
    assert next_variation(game, Browse(2, 1, 2), added) == Browse(2, 2, 1)  # From its first move.
    assert next_variation(game, Browse(2, 2, 2), added) == Browse(2)  # Then back to the game at the move.
    assert step_game(game, Browse(2, 2, 1), 1, added) == Browse(2, 2, 2)  # → plays it forward.
    assert step_game(game, Browse(2, 2, 2), -1, added) == Browse(2, 2, 1)  # ← plays it back.
    view = browse_view(game, Browse(2, 2, 2), added)
    assert view.marks == {(0, 0): (MARK_ACTUAL,), (4, 2): (MARK_COMPARE,), (5, 2): (MARK_COMPARE,)}


def test_the_end_of_a_sequence():
    """Only a sequence shown to its last move is at its end."""
    from kentogo.gui.viewer_model import Browse, sequence_at_end

    game = branched()
    assert sequence_at_end(game, Browse(2, 1, 2)).moves[-1].gtp() == "G7"
    assert sequence_at_end(game, Browse(2, 1, 1)) is None and sequence_at_end(game, Browse(2)) is None


def test_the_game_after_some_moves():
    """position_after gives the game after a number of moves, moved into the game."""
    game = branched()
    assert len(game.position_after(1).moves) == 1
    assert len(game.position_after(99).moves) == len(game.position_after(game.last_position).moves)


def test_the_ai_commentary_is_hidden_with_the_comparison_models_sequence():
    """With the comparison model's sequence shown, only the user's notes are shown, as in the quiz."""
    from kentogo.common.types import Move
    from kentogo.gui.viewer_model import SOURCE_COMPARE, Browse, browse_comment_text, variations_at
    from kentogo.mistakes.problem import Variation

    game = record()
    added = {2: Variation((Move.from_gtp("C3", "W"),), SOURCE_COMPARE)}
    last = len(variations_at(game, 2, added)) - 1
    assert browse_comment_text(game, Browse(2, last, 1), added) == "note"
    assert browse_comment_text(game, Browse(2), added) == comment_text(game, 2)
