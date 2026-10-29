"""Tests for kentogo.record.game_record."""

from pysgf import GoGame

from kentogo.record.ai_comment import AI_HEADER, REVIEW_HEADER
from kentogo.record.game_record import (
    move_commentary,
    next_ai_position,
    next_position,
    previous_ai_position,
    read_game_record,
    review_text,
)
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR


def katrain(number: int, color: str, point: str, loss: float) -> str:
    """Make KaTrain's English text for a move."""
    return f"\nMove {number}: {color} {point}\nEstimated point loss: {loss:.1f}\nPV: {color}Q4\n{INTERNAL_MARKER}"


def ai(text: str, header: str = AI_HEADER, rest: str = "") -> str:
    """Make a comment with an AI commentary, as the script writes it."""
    return f"{header}\n{text}\n{SEPARATOR}\n{rest}"


# A 9x9 game with a handicap stone. White's move 1 at A1 is captured by black's moves 2 and 4.
GAME = (
    "(;GM[1]SZ[9]KM[0.5]RU[japanese]PB[Black]PW[White]RE[B+R]AB[ee]"
    f";W[ai]C[{ai('Too far.', rest=katrain(1, 'W', 'A1', 5.0))}]"
    ";B[ah]"
    f";W[cc]C[note{SEPARATOR}{katrain(3, 'W', 'C7', 1.0)}]"
    ";B[bi]"
    f";W[gg]C[{ai('A good game.', REVIEW_HEADER)}])"
)


def record():
    """Read GAME."""
    return read_game_record(GoGame.parse_sgf(GAME))


def test_moves_and_comments():
    """Each move has its number, its notes, KaTrain's evaluation and the AI commentary."""
    game = record()
    assert (game.size, game.komi, game.black_name, game.white_name, game.result) == (9, 0.5, "Black", "White", "B+R")
    assert [m.move.gtp() for m in game.moves] == ["A1", "A2", "C7", "B1", "G3"]
    first = game.moves[0]
    assert (first.number, first.ai_text, first.ai_review, first.katrain.points_lost) == (1, "Too far.", "", 5.0)
    assert first.katrain_text.startswith("Move 1: W A1\nEstimated point loss: 5.0")
    third = game.moves[2]
    assert (third.notes, third.katrain.points_lost, third.ai_text) == ("note", 1.0, "")
    assert (game.moves[4].ai_text, game.moves[4].ai_review) == ("", "A good game.")


def test_positions_and_captures():
    """Position 0 has the setup stones, and the captured stone is gone after the capturing move."""
    game = record()
    assert game.state(0).stones == {(4, 4): "B"}
    assert game.state(1).stones[(0, 0)] == "W"
    assert (0, 0) not in game.state(4).stones and game.state(4).captures == {"B": 1, "W": 0}
    assert game.final_state() == game.state(5) == game.state(99)
    assert game.state(-1) == game.state(0)
    assert game.move_at(0) is None and game.move_at(3).move.gtp() == "C7"


def test_moving_through_the_game():
    """Moving by steps stays inside the game, and the AI commentaries can be jumped to."""
    game = record()
    assert next_position(game, 0) == 1 and next_position(game, 5) == 5 and next_position(game, 2, -10) == 0
    assert game.ai_positions() == [1, 5]
    assert next_ai_position(game, 0) == 1 and next_ai_position(game, 1) == 5 and next_ai_position(game, 5) is None
    assert previous_ai_position(game, 5) == 1 and previous_ai_position(game, 1) is None
    assert move_commentary(game, 1) == "Too far." and move_commentary(game, 5) == "" and move_commentary(game, 0) == ""
    assert review_text(game) == "A good game."


def test_illegal_move_is_left_out():
    """A move on a stone that is already there is marked, and the rest of the game is still read."""
    game = read_game_record(GoGame.parse_sgf("(;SZ[9];B[ee];W[ee];B[aa])"))
    assert [m.illegal for m in game.moves] == [False, True, False]
    assert game.final_state().stones == {(4, 4): "B", (0, 8): "B"}


def test_branches_and_the_position_before_a_move():
    """Other branches at a move are kept with it, and the position before a move can be played on."""
    # Move 3 has two branches next to it: a taken-back move, and a longer line tried by the user.
    text = "(;GM[1]SZ[9]AB[ee];W[ai];B[ah](;W[dd])(;W[cc];B[bi];W[hh])(;W[gg];B[gc]))"
    game = read_game_record(GoGame.parse_sgf(text))
    assert [move.move.gtp() for move in game.moves] == ["A1", "A2", "C7", "B1", "H2"]  # The longest line.
    assert [[m.gtp() for m in branch] for branch in game.moves[2].branches] == [["D6"], ["G3", "G7"]]
    assert game.moves[0].branches == ()
    before = game.position_before(3)
    assert [m.gtp() for m in before.moves] == ["A1", "A2"] and before.next_color == "W"
    assert [m.gtp() for m in before.setup] == ["E5"]
    assert game.position_before(0).moves == ()
