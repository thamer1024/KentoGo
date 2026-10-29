"""Tests for kentogo.gui.texts, with the Japanese texts (see tests/conftest.py and test_languages.py)."""

from kentogo.common.types import Move, Position
from kentogo.gui.texts import (
    TEXTS,
    color_name,
    fill_step_text,
    history_text,
    notes_text,
    problem_info,
    result_text,
    sequence_name,
    sequence_order_text,
    sequence_text,
    skipped_games_text,
    skipped_text,
    text,
)
from kentogo.mistakes.problem import Problem
from kentogo.quiz.collect import SkippedGame
from kentogo.quiz.score import compare_with_actual
from kentogo.quiz.session import AnswerResult
from kentogo.seichi.arrangement import FillStep

PROBLEM = Problem(
    problem_id="p1",
    sgf_path="/games/KaTrain_game 2026-10-19.sgf",
    move_number=169,
    position=Position(19, 6.5, "japanese", (), (), "B"),
    actual_move=Move.from_gtp("H1", "B"),
    best_move=Move.from_gtp("Q14", "B"),
    points_lost=7.5,
)


def test_all_texts_can_be_filled():
    """Every text can be used with its values (a wrong key name would fail here)."""
    values = {
        "game": "g",
        "move_number": 1,
        "color": "黒",
        "index": 1,
        "total": 2,
        "actual": 1.0,
        "answer": 0.5,
        "improvement": 0.5,
        "ratio": 0.5,
        "best": "Q4",
        "name": "n",
        "detail": "d",
        "names": "a → b",
        "result": "B+3.5",
        "black_areas": "30 + 7",
        "white_areas": "20",
        "verdict": "v",
        "komi": "6.5",
        "margin": "10.5",
        "moves": 200,
        "black": 10,
        "white": 8,
        "new_black": 9,
        "new_white": 8,
        "placed": 3,
        "compare": "Q3",
        "seconds": 5,
        "move": "Q3",
        "leader": "黒",
        "ahead": 3.5,
        "player": "白",
        "loss": 0.5,
        "gain": 4.5,
        "path": "p",
        "explanation": "e",
        "count": 3,
        "step": 1,
        "reason": "r",
        "labels": "l",
        "folder": "f",
        "limit": 30,
        "details": "d",
        "left": 5,
        "done": 1,
        "new": 2,
        "review": 3,
        "last": "l",
        "number": 2,
        "point": "Q3",
        "source": "Q3",
        "target": "R4",
        "confirmed_black": 10,
        "black_total": 3,
        "white_total": 21,
        "lead": "黒が 2 目多い",
        "points": "2",
        "confirmed_white": 8,
        "backup": "b",
        "where": "w",
        "field": "f",
        "section": "s",
        "model": "m",
        "input": 1,
        "output": 2,
        "env": "E",
        "played": "p",
        "size": 3,
        "goal": 5,
        "rank": "18k",
        "taken_back": "",
        "targets": "",
        "main": 500,
        "estimate": 100,
        "speed": 120,
        "compare_speed": 60,
    }
    for key in TEXTS:
        assert text(key, **values)


def test_color_name():
    """Colors have Japanese names."""
    assert (color_name("B"), color_name("W")) == ("黒", "白")


def test_sequence_name():
    """Known sources have names, and an unknown source is shown as it is."""
    assert sequence_name("katrain") == "最善手の手順（KaTrain）"
    assert sequence_name("katago") == "あなたの手の続き（KataGoの予想）"
    assert sequence_name("katago_actual") == "実戦の手の続き（KataGoの予想）"
    assert sequence_name("other") == "other"


def test_sequence_text():
    """The shown sequence has its name, an explanation, which of the sequences it is, and the move count."""
    shown = sequence_text("katago", index=2, count=3, step=4, total=12)
    assert "表示中：あなたの手の続き（KataGoの予想）" in shown
    assert "あなたが打った手の後" in shown
    assert "手順 2 / 3" in shown and "4 / 12 手目" in shown


def test_problem_info():
    """The information shows the file name without folder and extension, the move and the count."""
    info = problem_info(PROBLEM, 3, 29)
    assert "KaTrain_game 2026-10-19" in info
    assert "169手目" in info and "黒番" in info and "3 / 29" in info


def test_result_text_correct():
    """A correct answer shows the losses and the score."""
    result = AnswerResult(Move.from_gtp("Q14", "B"), 0.0, compare_with_actual(7.5, 0.0), True)
    shown = result_text(PROBLEM, result)
    assert "正解" in shown and "不正解" not in shown
    assert "実戦 7.5目損 → 打った手 Q14 0.0目損（+7.5目）" in shown
    assert "100%" in shown
    assert "打った手 Q14　実戦 H1　最善 Q14" in shown


def test_result_text_by_the_comparison_model():
    """With the comparison model's sequence, only its move's loss is shown: no verdict, no other losses."""
    result = AnswerResult(Move.from_gtp("R4", "B"), 1.0, compare_with_actual(5.0, 1.0), True)
    compare = {"compare_best": Move.from_gtp("Q3", "B"), "by_compare": True, "show_verdict": False}
    gain = result_text(PROBLEM, result, **compare, compare_best_loss=0.5)
    assert gain.startswith("[color=d070f0]比較用モデルの手 Q3：0.5目損（実戦より 4.5目得）")
    assert "正解" not in gain and "打った手 R4 1.0目損" not in gain and "80%" not in gain
    assert "比較 Q3" in gain and "☆比較用モデル" in gain
    worse = result_text(PROBLEM, result, **compare, compare_best_loss=6.0)
    assert "（実戦より 1.0目損）" in worse
    waiting = result_text(PROBLEM, result, **compare)  # Its loss is not known yet: the losses of the answer.
    assert "実戦 5.0目損 → 打った手 R4 1.0目損（+4.0目）" in waiting
    assert "比較用モデル" not in result_text(PROBLEM, result)  # Without the comparison model.
    shaped = result_text(PROBLEM, result, compare_best=Move.from_gtp("Q3", "B"))
    assert "○打った手" in shaped and "△実戦" in shaped and "□最善" in shaped and "☆比較用モデル" in shaped


def test_result_text_not_judged():
    """An answer without a known loss shows why it is not judged yet."""
    result = AnswerResult(Move.from_gtp("R4", "B"), None, None, None)
    shown = result_text(PROBLEM, result, text("evaluating"))
    assert "判定待ち" in shown
    assert "KataGoで計算しています" in shown
    assert "打った手 R4" in shown


def test_settings_screen_has_all_texts():
    """Every input of the settings screen has a name, and every order has a name."""
    from kentogo.gui.settings_form import FIELDS, PAGES
    from kentogo.katago.engine_settings import JUDGE_MODELS
    from kentogo.quiz.quiz_settings import ORDERS
    from kentogo.repetition.modes import PRIORITIES, REVIEW_MODES

    for spec in FIELDS:
        assert f"field_{spec.id}" in TEXTS
        for choice in spec.choices:
            assert f"{spec.id}_{choice}" in TEXTS
    for order in ORDERS:
        assert f"order_{order}" in TEXTS
    for priority in PRIORITIES:
        assert f"priority_{priority}" in TEXTS
    for mode in REVIEW_MODES:
        assert f"review_mode_{mode}" in TEXTS
    for page in PAGES:
        assert f"page_{page}" in TEXTS
    for model in JUDGE_MODELS:
        assert f"judge_model_{model}" in TEXTS


def test_notes_text():
    """The notes are shown as they are; without notes nothing is shown."""
    assert notes_text("D4 is bigger") == "D4 is bigger"
    assert notes_text("") == ""


def test_history_text():
    """The line tells how many times the problem is asked, and the last result."""
    from dataclasses import replace

    from kentogo.review.record import AnswerRecord

    record = AnswerRecord("p1", "t", "g.sgf", 3, "B", "Q4", "A19", "Q4", 0.0, 8.0, "sgf", None, True, 0, False)
    assert history_text([]) == "この問題：初めて"
    assert history_text([record]).startswith("この問題：2回目（前回 ")
    assert "不正解" in history_text([record, replace(record, correct=False)])
    assert "判定なし" in history_text([replace(record, correct=None)])


def test_skipped_text():
    """Games without problems are counted by reason. Without any, there is no line."""
    assert skipped_text({}) == ""
    line = skipped_text({"no_analysis": 1, "unknown_color": 2})
    assert "KaTrainの分析が無い 1局" in line and "自分の色がわからない 2局" in line
    assert "other 3" in skipped_text({"other": 3})


def test_skipped_games_text():
    """Each game that gave no problems is shown on its own line with the reason."""
    games = [
        SkippedGame("a.sgf", "unknown_color"),
        SkippedGame("b.sgf", "cannot_read", "broken"),
        SkippedGame("c.sgf", "x"),
    ]
    lines = skipped_games_text(games).split("\n")
    assert lines[0].startswith("a.sgf：自分の色がわからない")
    assert lines[1] == "b.sgf：読めない（broken）"
    assert lines[2] == "c.sgf: x"  # A reason without a text (not expected) is shown as it is.


def test_sequence_order_text():
    """The order line names every sequence, marks the shown one, and tells which are still calculated."""
    line = sequence_order_text([("katago", "waiting"), ("katrain", ""), ("katago_compare", "failed")], 1, 12)
    assert line.startswith("Tabで切替：あなたの手(考え中 12秒) → ")
    assert "▶棋譜(KaTrain)" in line and "比較用モデル(失敗)" in line
    assert "比較用モデル(選ぶと計算)" in sequence_order_text([("katago_compare", "offered")], 0)


def test_sequence_text_while_waiting():
    """While KataGo is calculating, the text says so instead of the move count."""
    shown = sequence_text("katago_compare", index=1, count=2, step=0, total=0, status="waiting")
    assert "表示中：比較用モデルの最善手順" in shown and "考えています" in shown and "手目" not in shown


def test_fill_step_text():
    """Each step of the computer's seichi is told with its points."""
    point = Move.from_gtp("Q3", "B").coord
    other = Move.from_gtp("R4", "B").coord
    place = FillStep("place", "W", (point,), {}, {})
    move = FillStep("move", "B", (point, other), {}, {})
    change = FillStep("exchange", "B", (point, other), {}, {})
    recolor = FillStep("exchange", "W", (other,), {}, {})
    swap = FillStep("swap", "B", (point, other), {}, {})
    assert "白のアゲハマを Q3" in fill_step_text(place, 1, 3)
    assert "黒石を △Q3 から ○R4 へ動かす" in fill_step_text(move, 2, 3)
    assert "△Q3 の黒石を碁笥に戻し、白の碁笥から白石を ○R4 に置く" in fill_step_text(change, 3, 3)
    assert "○R4 の白石を碁笥に戻し、黒の碁笥から黒石を R4 に置く" in fill_step_text(recolor, 3, 3)
    assert "△Q3 の黒石と ○R4 の白石を入れ替える" in fill_step_text(swap, 3, 3)
    assert "0 / 3" in fill_step_text(None, 0, 3)


def test_lead_text():
    """The lead is told for black, white, or even; with komi, who wins."""
    from kentogo.gui.texts import lead_text

    assert lead_text(2) == "黒が 2 目多い" and lead_text(-3) == "白が 3 目多い" and lead_text(0) == "差なし"
    assert lead_text(2 - 6.5, 6.5) == "コミ 6.5 目を入れると、白の 4.5 目勝ち"


def test_notes_text_with_ai_comment():
    """The AI commentary comes first under its heading, then the user's notes."""
    assert notes_text("", ai_comment="Q4 first") == f"{TEXTS['ai_commentary']}\nQ4 first"
    assert notes_text("my note", ai_comment="Q4 first") == f"{TEXTS['ai_commentary']}\nQ4 first\n\nmy note"


def test_notice_text():
    """A message given by a part without screens is put into words; None gives ""."""
    from kentogo.gui.texts import notice_text, notices_text
    from kentogo.notice import Notice

    notice = Notice("notice_settings_broken", {"reason": "r"})
    assert notice_text(notice) == text("notice_settings_broken", reason="r")
    assert notice_text(None) == ""
    assert notices_text([notice, Notice("nothing_today")]) == f"{notice_text(notice)}\n\n{text('nothing_today')}"


def test_result_text_of_another_sequence():
    """While another sequence is shown, the line of the losses tells about its first move."""
    result = AnswerResult(Move.from_gtp("Q14", "B"), 0.0, compare_with_actual(7.5, 0.0), True)
    shown = result_text(PROBLEM, result, sequence=(Move.from_gtp("R4", "B"), 2.5))
    assert "実戦 7.5目損 → 打った手 R4 2.5目損（+5.0目）" in shown
    unknown = result_text(PROBLEM, result, sequence=(Move.from_gtp("R4", "B"), None))
    assert "実戦 7.5目損 → 打った手 R4（損失はわかりません）" in unknown


def test_count_check_text():
    """Right or wrong, the territory on the board, and the right territory with komi are always shown."""
    from kentogo.gui.texts import count_check_text
    from kentogo.seichi.count_check import CountCheck
    from kentogo.seichi.territory import TerritoryCount

    right = TerritoryCount(52, 45)
    good = count_check_text(CountCheck(right, right, {"B": 0, "W": 0}), 6.5)
    assert good.startswith("正解") and "整地：正解" in good
    assert "正しい地　黒 52目　白 45目" in good and "黒の 0.5 目勝ち" in good
    left = count_check_text(CountCheck(right, TerritoryCount(53, 45), {"B": 1, "W": 0}), 6.5)
    assert left.startswith("正解") and "残ったアゲハマ 1 個" in left
    bad = count_check_text(CountCheck(right, TerritoryCount(50, 45), {"B": 1, "W": 0}), 6.5)
    assert bad.startswith("間違い") and "盤上の地　黒 49目　白 45目" in bad and "残ったアゲハマ 1 個" in bad


def test_result_text_without_the_verdict():
    """With another sequence than the answer's, correct or wrong (or why it waits) is not shown."""
    result = AnswerResult(Move.from_gtp("Q14", "B"), 0.0, compare_with_actual(7.5, 0.0), True)
    shown = result_text(PROBLEM, result, show_verdict=False)
    assert "正解" not in shown and "実戦 7.5目損" in shown
    waiting = AnswerResult(Move.from_gtp("Q14", "B"), None, None, None)
    assert "判定待ち" not in result_text(PROBLEM, waiting, text("evaluating"), show_verdict=False)


def test_problem_info_is_two_lines():
    """The game is on the first line; the move, the player and the count on the second."""
    info = problem_info(PROBLEM, 3, 29)
    assert info.count("\n") == 1 and info.splitlines()[1] == "169手目　黒番　問題 3 / 29"
