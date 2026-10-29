"""Tests for kentogo.quiz.notes_transform."""

from kentogo.common.types import Move
from kentogo.quiz.notes_transform import DIRECTION_FAMILIES, transform_notes
from kentogo.quiz.transform import SYMMETRIES, BoardTransform

ROTATE = BoardTransform(1)  # 90 degrees clockwise: the bottom left corner goes to the top left.
FLIP = BoardTransform(4)  # Left to right.
SWAP = BoardTransform(0, swap_colors=True)


def test_nothing_changes_without_a_transform():
    """Without a change, the notes are the same."""
    notes = "黒D17で左上を守ります。"
    assert transform_notes(notes, BoardTransform(), 19) == notes


def test_points_match_the_moves():
    """A point in the notes becomes the same point as the changed move."""
    for symmetry in SYMMETRIES:
        transform = BoardTransform(symmetry)
        for gtp in ("A1", "D17", "Q4", "T19", "K10"):
            expected = transform.move(Move.from_gtp(gtp, "B"), 19).gtp()
            assert transform_notes(f"実戦の{gtp}は", transform, 19) == f"実戦の{expected}は"


def test_points_in_ranges_and_lists():
    """Points next to Japanese letters, ranges and lists are all rewritten."""
    assert transform_notes("G5〜K5、K4・O3", FLIP, 19) == "N5〜K5、K4・F3"


def test_points_with_the_color_first():
    """A point written with its color first, as KaTrain does ("BJ11"), is rewritten too; B4 alone is a point."""
    assert transform_notes("推奨手のBJ11、WQ16、B4", FLIP, 19) == "推奨手のBL11、WD16、S4"
    assert transform_notes("推奨手のBJ11、B4", SWAP, 19) == "推奨手のWJ11、B4"


def test_other_words_stay():
    """Words that only look like points, numbers and lower case names are not rewritten."""
    notes = "PV: b18c384 AI 12位 8.4目 第36手目 5の段 S20 BQ4X"
    assert transform_notes(notes, ROTATE, 19) == notes


def test_points_outside_the_board_stay():
    """A point that is not on the board (here a 9x9 board) is not rewritten."""
    assert transform_notes("K10 と J9", FLIP, 9) == "K10 と A9"


def test_colors_are_swapped_only_when_asked():
    """黒 and 白 (and Black and White) are swapped only when the colors are swapped."""
    assert transform_notes("黒E18に白D18、白+0.3、Black wins", SWAP, 19) == "白E18に黒D18、黒+0.3、White wins"
    assert transform_notes("黒E18", FLIP, 19) == "黒P18"


def test_directions_rotate_with_the_board():
    """Directions turn with the board, and each family keeps its own words."""
    assert transform_notes("左上の戦い、右辺、下側", ROTATE, 19) == "右上の戦い、下辺、左側"
    assert transform_notes("左上と右下", FLIP, 19) == "右上と左下"
    assert transform_notes("upper left, top right, left side", ROTATE, 19) == "upper right, bottom right, top side"


def test_each_word_is_rewritten_once():
    """Rewritten words are not rewritten again: swapping colors twice in one text does not happen."""
    assert transform_notes("黒白", SWAP, 19) == "白黒"


def test_every_direction_has_a_word_after_every_change():
    """Every direction word has a word in its family after every change, so no word is lost."""
    for symmetry in SYMMETRIES:
        for family in DIRECTION_FAMILIES:
            for word in family.values():
                assert transform_notes(word, BoardTransform(symmetry), 19) in family.values()
