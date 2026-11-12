"""Tests for kentogo.commentary.move_facts and commentary.fact_lines (the shapes around a mistake).

The 55th move of the sample of the user's own prototype (kento_prompt): black hanes at O2 instead of
cutting at O4, and white connects at O4.
"""

from kentogo.commentary.diagram import Region
from kentogo.commentary.fact_lines import fact_lines
from kentogo.commentary.move_facts import GameMoves, move_facts
from kentogo.commentary.prompt_words import ENGLISH_WORDS, JAPANESE_WORDS
from kentogo.common.board import Board
from kentogo.common.shapes import CONNECT, CUT, HANE
from kentogo.common.types import Move, Position, moves_from_gtp

WHOLE = Region.whole(19)


def board(black: str = "", white: str = "") -> Board:
    """A 19x19 board with black and white stones (GTP points separated by spaces)."""
    stones = [Move.from_gtp(p, "B") for p in black.split()] + [Move.from_gtp(p, "W") for p in white.split()]
    return Board.from_position(Position(19, 6.5, "japanese", tuple(stones), (), "B"))


def facts(sequence: str = "O4 O2", reply: str | None = "O4", opponent_best: str | None = "O4"):
    """The facts of the move: black O2 after white's wedge at O3."""
    before_last = board("N3 P3 Q3 R3", "P4 Q4 R4")
    before = board("N3 P3 Q3 R3", "O3 P4 Q4 R4")
    game = GameMoves(
        Move.from_gtp("O3", "W"),
        Move.from_gtp(reply, "W") if reply else None,
        Move.from_gtp(opponent_best, "W") if opponent_best else None,
    )
    return move_facts(before_last, before, Move.from_gtp("O2", "B"), moves_from_gtp(sequence.split(), "B"), game)


def test_the_shapes_of_the_moves():
    found = facts()
    assert [shape.name for shape in found.played.shapes] == [HANE]
    assert [shape.name for shape in found.best.shapes] == [CUT]
    assert [shape.name for shape in found.game[1].shapes] == [CONNECT]
    assert found.played.in_atari[0].stones == (Move.from_gtp("O3", "W").coord,)


def test_the_cutting_points_after_the_game():
    found = facts()
    assert found.cuts_before == ()
    assert found.cuts_after_game == (Move.from_gtp("N2", "B").coord, Move.from_gtp("P2", "B").coord)


def test_the_groups_near_the_opponents_best_move():
    stones = {group.stones[0] for group in facts().aimed_at}
    assert Move.from_gtp("N3", "B").coord in stones and Move.from_gtp("O2", "B").coord in stones


def test_without_a_reply_or_the_opponents_best_move():
    found = facts(reply=None, opponent_best=None)
    assert len(found.game) == 1 and found.aimed_at == ()


def test_the_japanese_lines():
    lines = fact_lines(facts(), 19, WHOLE, JAPANESE_WORDS)
    assert "  [形] 相手の直前の手 白O3(右下,3線): ワリコミ(黒N3,黒P3の間)" in lines
    assert "  [形] 実戦の手 黒O2(右下,2線): ハネ(黒N3,黒P3から)、アテ(白の石 O3(1子)がアタリ)" in lines
    assert "  [形] 最善手 黒O4(右下,4線): キリ(白O3,白P4を切る)、アテ(白の石 O3(1子)がアタリ)" in lines
    assert "  白O4(右下,4線): ツギ(白O3,白P4をつなぐ)" in lines
    assert "  [予想手順の相手の次の手] 白は最善手の近く(2路)のO2(右下,2線)に打つ." in lines
    cuts = "  [切られる点](黒の石.拡大図の範囲) 直前: なし / 実戦の進行の後: N2,P2 / 予想手順の後: N4"
    assert cuts in lines


def test_a_move_far_from_the_best_move():
    lines = fact_lines(facts(sequence="O4 C17"), 19, WHOLE, JAPANESE_WORDS)
    assert "  [予想手順の相手の次の手] 白は手を抜いてC17(左上隅,3線)に打つ(最善手から13路)." in lines


def test_the_cutting_points_only_in_the_zoomed_board():
    lines = fact_lines(facts(), 19, Region(0, 0, 13, 18), JAPANESE_WORDS)
    assert any("実戦の進行の後: N2 /" in line for line in lines)


def test_the_english_lines():
    lines = fact_lines(facts(), 19, WHOLE, ENGLISH_WORDS)
    assert (
        "  [Shape] Best move Black O4 (bottom right, line 4): cut (White O3,White P4), atari (White stones O3 (count: 1) in atari)"
        in lines
    )
