"""Tests for kentogo.commentary.material."""

import base64
import gzip
import json

from pysgf import GoGame

from kentogo.commentary.material import GroupInfo, has_katrain_evaluation, make_material
from kentogo.common.types import Move
from kentogo.mistakes.extract import ExtractSettings
from kentogo.record.game_record import read_game_record
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR


def katrain(number: int, color: str, point: str, loss: float | None, best: str, pv: str) -> str:
    """Make KaTrain's English comment for a move."""
    text = f"\nMove {number}: {color} {point}\n"
    if loss is not None:
        text += f"Estimated point loss: {loss:.1f}\nPredicted top move was {best} (B+1.0).\n"
    return text + f"PV: {pv}\n{INTERNAL_MARKER}"


def kt(analysis: dict) -> str:
    """Make a KT property in the same way as KaTrain."""
    parts = [b"\x00" * 8, b"\x00" * 8, json.dumps(analysis).encode("utf-8")]
    return "KT" + "".join(f"[{base64.standard_b64encode(gzip.compress(part, mtime=0)).decode()}]" for part in parts)


BEFORE_3 = {"root": {"scoreLead": 2.0}, "moves": {"A2": {"scoreLead": 2.0}, "G7": {"scoreLead": -4.0}}}

# A 9x9 game. Black (the user) loses 6.0 points with move 3 and 3.5 points with move 5.
# The best move of move 3 (A2) takes the white stone at A1. In the sequence of move 5,
# the last move (B3) puts the white stone at C3 in atari.
GAME = (
    "(;GM[1]SZ[9]KM[6.5]RU[japanese]"
    f";B[bi]C[{katrain(1, 'B', 'B1', None, 'B1', 'BB1')}]"
    f";W[ai]{kt(BEFORE_3)}"
    f";B[gc]{kt({'root': {'scoreLead': -4.0}, 'moves': {}})}C[my note{SEPARATOR}{katrain(3, 'B', 'G7', 6.0, 'A2', 'BA2 C3')}]"
    f";W[cg]C[{katrain(4, 'W', 'C3', 2.0, 'D4', 'WD4 E4')}]"
    f";B[de]C[{katrain(5, 'B', 'D5', 3.5, 'C2', 'BC2 E5 C4 F5 B3')}]"
    ";W[ec])"
)


def material(count: int = 5):
    """Make the material of GAME for black."""
    return make_material(GoGame.parse_sgf(GAME), "B", ExtractSettings(problems_per_game=count))


def test_biggest_mistakes_in_the_order_played():
    """The biggest losses are chosen, and given in the order they were played."""
    game = material()
    assert [(m.number, m.points_lost) for m in game.moves] == [(3, 6.0), (5, 3.5)]
    assert [m.number for m in material(1).moves] == [3]
    assert (game.size, game.komi, game.my_color, game.final_number) == (9, 6.5, "B", 6)


def test_loss_counts():
    """The user's moves are counted by the size of their loss."""
    assert material().loss_counts == ((20, 0), (12, 0), (10, 0), (8, 0), (6, 1), (3, 2))


def test_move_facts():
    """A mistake has the board before it, the best move, the sequence played on the board, and more."""
    move = material().moves[0]
    assert move.played == Move.from_gtp("G7", "B") and move.best_move == Move.from_gtp("A2", "B")
    assert move.before.stones == {(1, 0): "B", (0, 0): "W"}
    assert move.last_move == Move.from_gtp("A1", "W")
    assert [step.move.gtp() for step in move.pv_steps] == ["A2", "C3"]
    assert move.pv_steps[0].captured == ((0, 0),)  # A2 takes the white stone at A1.
    assert (0, 0) not in move.after_pv.stones and move.after_pv.captures["B"] == 1
    assert move.nearby == (GroupInfo("W", ((0, 0),), 1), GroupInfo("B", ((1, 0),), 2))
    assert move.candidates == (("A2", 0.0), ("G7", 6.0))
    assert move.score_after == -4.0
    assert move.notes == "my note"
    assert move.katrain_text.startswith("Move 3: B G7\nEstimated point loss: 6.0")
    reply = move.reply
    assert (reply.move.gtp(), reply.points_lost, reply.best_move) == ("C3", 2.0, "D4")
    assert [m.gtp() for m in reply.pv] == ["D4", "E4"]


def test_new_atari_in_the_sequence():
    """A group is told to be in atari only at the move that puts it in atari."""
    steps = material().moves[1].pv_steps
    assert [step.in_atari for step in steps[:4]] == [(), (), (), ()]  # A1 was in atari before: not told again.
    assert steps[4].in_atari == (GroupInfo("W", ((2, 2),), 1),)


def test_without_analysis_data_or_reply():
    """Without KT there are no candidates and no score, and the last move has no reply."""
    move = material().moves[1]
    assert (move.candidates, move.score_after) == ((), None)
    assert move.reply.move.gtp() == "E7"
    assert material().moves[1].reply.points_lost is None


def test_has_katrain_evaluation():
    """A game is analyzed if KaTrain wrote the loss of any of the user's moves."""
    record = read_game_record(GoGame.parse_sgf(GAME))
    assert has_katrain_evaluation(record, "B")
    assert has_katrain_evaluation(record, "W")  # White's move 4 has a loss too.
    assert not has_katrain_evaluation(read_game_record(GoGame.parse_sgf("(;SZ[9];B[ee];W[cc])")), "B")


def test_decided_positions_wait():
    """A move in a decided position (from the analysis data before it) is chosen only when there is room."""
    decided = {"root": {"scoreLead": 30.0, "winrate": 0.99}, "moves": {"A2": {"scoreLead": 30.0}}}
    text = GAME.replace(f";W[ai]{kt(BEFORE_3)}", f";W[ai]{kt(decided)}")
    root = GoGame.parse_sgf(text)
    assert [m.number for m in make_material(root, "B", ExtractSettings(problems_per_game=1)).moves] == [
        5
    ]  # Move 3 lost more, but was decided.
    assert [m.number for m in make_material(root, "B", ExtractSettings(problems_per_game=2)).moves] == [3, 5]


def test_the_moves_are_the_problems_of_the_quiz():
    """The same conditions as the quiz: the smallest loss and the opening moves left out are used too."""
    root = GoGame.parse_sgf(GAME)
    assert [m.number for m in make_material(root, "B", ExtractSettings(min_points_lost=4.0)).moves] == [3]
    assert [m.number for m in make_material(root, "B", ExtractSettings(skip_opening_moves=3)).moves] == [5]
    assert make_material(root, "B", ExtractSettings(min_points_lost=10.0)).moves == ()


def test_a_move_taken_back_is_explained_when_the_quiz_uses_it():
    """A move KaTrain took back is explained when it is a problem of the quiz (it has no reply)."""
    undone = katrain(5, "B", "A9", 30.0, "C2", "BC2").replace(
        INTERNAL_MARKER, f"Move was automatically undone in teaching mode.\n{INTERNAL_MARKER}"
    )
    small = f";B[de]C[{katrain(5, 'B', 'D5', 1.0, 'C2', 'BC2')}]"  # Move 5 is not a problem.
    game = GAME.replace(f";B[de]C[{katrain(5, 'B', 'D5', 3.5, 'C2', 'BC2 E5 C4 F5 B3')}]", small)
    root = GoGame.parse_sgf(game.replace(small, f"(;B[aa]C[{undone}])({small}", 1) + ")")
    with_undone = ExtractSettings(problems_per_game=1, include_undone_moves=True)
    (move,) = make_material(root, "B", with_undone).moves  # The quiz's one problem is the move taken back.
    assert (move.number, move.played.gtp(), move.points_lost, move.taken_back) == (5, "A9", 30.0, True)
    assert move.reply is None and move.best_move.gtp() == "C2"
    from kentogo.commentary.prompt import PlayerInfo, build_prompt
    from kentogo.commentary.prompt_text import default_prompt_text

    prompt = build_prompt(make_material(root, "B", with_undone), PlayerInfo("18k", "same"), default_prompt_text())
    assert "第5手目(黒番,KaTrainの指導碁で待ったをした手)" in prompt.user
    assert [m.number for m in make_material(root, "B", ExtractSettings(problems_per_game=1)).moves] == [3]
