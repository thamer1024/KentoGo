"""Tests for kentogo.commentary.sgf_writer."""

from datetime import datetime

import pytest

from kentogo.commentary.answer import Answer, AnswerProblem
from kentogo.commentary.material import make_material
from kentogo.commentary.sgf_writer import backup_file, move_comment_text, review_comment_text, write_commentary
from kentogo.common import sgf
from kentogo.record.ai_comment import AI_HEADER, REVIEW_HEADER, split_ai_comment
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR


def katrain(number: int, color: str, point: str, loss: float, best: str) -> str:
    """Make KaTrain's English comment for a move."""
    return (
        f"\nMove {number}: {color} {point}\nEstimated point loss: {loss:.1f}\n"
        f"Predicted top move was {best} (B+1.0).\nPV: {color}{best}\n{INTERNAL_MARKER}"
    )


# Black (the user) loses points with moves 1, 3 and 5; move 5 is the last move.
# White's move 2 has an old AI commentary, which is removed.
GAME = (
    "(;GM[1]FF[4]CA[UTF-8]SZ[9]KM[6.5]KT[keep]"
    f";B[ee]C[note{SEPARATOR}{katrain(1, 'B', 'E5', 4.0, 'C3')}]"
    f";W[cg]C[{AI_HEADER}\nold text\n{SEPARATOR}\n{katrain(2, 'W', 'C3', 1.0, 'D4')}]"
    f";B[gc]C[{katrain(3, 'B', 'G7', 6.0, 'D4')}]"
    ";W[df]"
    f";B[bh]C[{katrain(5, 'B', 'B2', 5.0, 'F5')}])"
)
FIELDS = {"situation": "戦い", "category": "misread", "what_happened": "a", "aim": "b", "lesson": "c"}
SUMMARY = {"category_counts": "読み違い 3", "main_issue": "x", "next_focus": "y", "loss_comparison": "z"}
NOW = datetime(2026, 10, 23, 16, 30, 0)


def game_file(tmp_path):
    """Write GAME to a file and return its path."""
    path = tmp_path / "game.sgf"
    path.write_text(GAME, encoding="utf-8")
    return path


def comments(path) -> list[str]:
    """Return the comments of the moves of the main line."""
    nodes = sgf.main_line(sgf.load_game(path))[1:]
    return [str(node.get_property("C", "")) for node in nodes]


def test_write_commentary(tmp_path):
    """Each explained move gets its commentary, the last move also the review, and old commentary is removed."""
    path = game_file(tmp_path)
    material = make_material(sgf.load_game(path), "B")
    answer = Answer({1: FIELDS, 3: FIELDS, 5: FIELDS}, SUMMARY, ())
    result = write_commentary(path, material, answer, "18k", now=lambda: NOW)
    assert result.moves == (1, 3, 5)
    assert result.backup == tmp_path / "game.sgf.20261023-163000.bak"
    assert result.backup.read_text(encoding="utf-8") == GAME
    first, second, third, _, last = (split_ai_comment(comment) for comment in comments(path))
    assert first.move_text.startswith("(実戦 E5 → 最善 C3,損失 4.0目)\n・局面: 戦い\n・分類: 読み違い")
    assert first.rest.startswith("note")  # The user's notes and KaTrain's text are kept.
    assert (second.move_text, second.review_text) == ("", "")
    assert third.move_text.startswith("(実戦 G7 → 最善 D4,損失 6.0目)")
    assert last.move_text.startswith("(実戦 B2 → 最善 F5,損失 5.0目)")
    assert last.review_text.startswith("損失目数が大きい上位3手を特定しました.")
    assert sgf.load_game(path).get_property("KT") == "keep"  # Other properties are kept.


def test_written_again_replaces_the_commentary(tmp_path):
    """Writing again replaces the commentary instead of adding another one."""
    path = game_file(tmp_path)
    material = make_material(sgf.load_game(path), "B")
    write_commentary(path, material, Answer({1: FIELDS, 3: FIELDS, 5: FIELDS}, SUMMARY, ()), "18k", now=lambda: NOW)
    new_fields = {**FIELDS, "lesson": "new lesson"}
    write_commentary(path, material, Answer({1: new_fields, 3: FIELDS, 5: FIELDS}, SUMMARY, ()), "", now=lambda: NOW)
    first = comments(path)[0]
    assert first.count(AI_HEADER) == 1 and "・教訓: new lesson" in first
    assert comments(path)[-1].count(REVIEW_HEADER) == 1
    assert (tmp_path / "game.sgf.20261023-163000-2.bak").exists()  # The first copy is not overwritten.


def test_refused_answers_and_changed_files(tmp_path):
    """An answer with errors, or a file whose moves changed, is not written."""
    path = game_file(tmp_path)
    material = make_material(sgf.load_game(path), "B")
    with pytest.raises(ValueError):
        write_commentary(path, material, Answer({}, {}, (AnswerProblem("no_summary"),)), "18k")
    path.write_text(GAME.replace(";B[gc]", ";B[gd]"), encoding="utf-8")
    with pytest.raises(ValueError):
        write_commentary(path, material, Answer({1: FIELDS, 3: FIELDS, 5: FIELDS}, SUMMARY, ()), "18k")
    assert list(tmp_path.glob("*.bak")) == []


def test_texts(tmp_path):
    """The texts are in the same form as the user's script."""
    material = make_material(sgf.load_game(game_file(tmp_path)), "B")
    text = move_comment_text(material.moves[1], {**FIELDS, "lesson": ""})
    assert (
        text
        == "(実戦 G7 → 最善 D4,損失 6.0目)\n・局面: 戦い\n・分類: 読み違い\n・何が起きたか: a\n・最善手と予想手順の狙い: b"
    )
    review = review_comment_text(material, "18k", SUMMARY)
    assert review.splitlines()[:5] == [
        "損失目数が大きい上位3手を特定しました.",
        " - 第 3 手目 (黒) (損失: 6.0目 / 最善手: D4)",
        " - 第 5 手目 (黒) (損失: 5.0目 / 最善手: F5)",
        " - 第 1 手目 (黒) (損失: 4.0目 / 最善手: C3)",
        "",
    ]
    assert "・3目以上: 3回(目標 11回,超えてはいけない 23回)" in review
    assert review.endswith("・分類の集計: 読み違い 3\n・一番の課題: x\n・次の対局で意識すること: y\n・損失の回数: z")
    assert "(段級位の行が目標表に無いため,目標との比較はありません)" in review_comment_text(material, "", SUMMARY)


def test_backup_names(tmp_path):
    """A copy never overwrites an earlier copy."""
    path = game_file(tmp_path)
    assert backup_file(path, NOW).name == "game.sgf.20261023-163000.bak"
    assert backup_file(path, NOW).name == "game.sgf.20261023-163000-2.bak"


def test_a_move_taken_back_gets_its_commentary_in_its_branch(tmp_path):
    """A move KaTrain took back gets its commentary in its branch; written again without it, it is removed."""
    from kentogo.mistakes.extract import ExtractSettings

    undone = katrain(3, "B", "A9", 9.0, "D4").replace(
        INTERNAL_MARKER, f"Move was automatically undone in teaching mode.\n{INTERNAL_MARKER}"
    )
    small = f";B[gc]C[{katrain(3, 'B', 'G7', 1.0, 'D4')}]"  # Move 3 of the game is not a problem.
    text = GAME.replace(f";B[gc]C[{katrain(3, 'B', 'G7', 6.0, 'D4')}]", f"(;B[aa]C[{undone}]){small}", 1)
    text = text.replace(f"(;B[aa]C[{undone}]){small}", f"(;B[aa]C[{undone}])({small}", 1) + ")"
    path = tmp_path / "game.sgf"
    path.write_text(text, encoding="utf-8")
    conditions = ExtractSettings(include_undone_moves=True)
    material = make_material(sgf.load_game(path), "B", conditions)
    assert [(move.number, move.taken_back) for move in material.moves] == [(1, False), (3, True), (5, False)]
    write_commentary(path, material, Answer({1: FIELDS, 3: FIELDS, 5: FIELDS}, SUMMARY, ()), "18k", now=lambda: NOW)
    root = sgf.load_game(path)
    branch = next(node for node in sgf.main_line(root)[2].children if sgf.node_move(node).gtp() == "A9")
    assert split_ai_comment(str(branch.get_property("C", ""))).move_text.startswith("(待ったの手 A9")
    assert not split_ai_comment(comments(path)[2]).has_ai  # Move 3 of the game.
    material = make_material(sgf.load_game(path), "B")  # Now without the moves taken back.
    write_commentary(path, material, Answer({1: FIELDS, 5: FIELDS}, SUMMARY, ()), "18k", now=lambda: NOW)
    branch = next(node for node in sgf.main_line(sgf.load_game(path))[2].children if sgf.node_move(node).gtp() == "A9")
    assert not split_ai_comment(str(branch.get_property("C", ""))).has_ai


def test_texts_in_another_language(tmp_path):
    """The words around the answer and the names of the categories are those given (the language of the screens)."""
    from kentogo.commentary.language import CommentLabels

    labels = CommentLabels(
        bullet="- ",
        situation="Situation",
        category="Category",
        move_line="({played} {move} → best {best}, loss {loss} points)",
        actual="Played",
        loss_line="{size}+ points: {count} times{targets}",
        categories=("A", "B", "C", "Misread", "E"),
    )
    material = make_material(sgf.load_game(game_file(tmp_path)), "B")
    text = move_comment_text(material.moves[1], {"situation": "fight", "category": "misread"}, labels)
    assert text == "(Played G7 → best D4, loss 6.0 points)\n- Situation: fight\n- Category: Misread"
    assert "- 3+ points: 3 times(目標 11回,超えてはいけない 23回)" in review_comment_text(
        material, "18k", SUMMARY, labels
    )


def test_written_with_the_english_headers(tmp_path):
    """With the English headers, the old Japanese commentary is replaced, and the new one has the English headers."""
    from kentogo.commentary.language import CommentLabels
    from kentogo.record.ai_comment import AI_HEADER_EN, REVIEW_HEADER_EN

    path = game_file(tmp_path)
    material = make_material(sgf.load_game(path), "B")
    labels = CommentLabels(move_header=AI_HEADER_EN, review_header=REVIEW_HEADER_EN)
    write_commentary(
        path, material, Answer({1: FIELDS, 3: FIELDS, 5: FIELDS}, SUMMARY, ()), "18k", labels, now=lambda: NOW
    )
    text = "".join(comments(path))
    assert AI_HEADER not in text and REVIEW_HEADER not in text and "old text" not in text
    assert text.count(AI_HEADER_EN) == 3 and text.count(REVIEW_HEADER_EN) == 1
