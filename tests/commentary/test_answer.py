"""Tests for kentogo.commentary.answer."""

import json

from kentogo.commentary.answer import (
    PROBLEM_EMPTY_FIELD,
    PROBLEM_MISSING_MOVE,
    PROBLEM_NO_SUMMARY,
    PROBLEM_NOT_JSON,
    PROBLEM_UNKNOWN_CATEGORY,
    PROBLEM_UNKNOWN_MOVE,
    extract_json,
    read_answer,
)

FIELDS = {"situation": "戦い", "category": "misread", "what_happened": "a", "aim": "b", "lesson": "c"}
SUMMARY = {"category_counts": "読み違い 2", "main_issue": "x", "next_focus": "y", "loss_comparison": "z"}


def answer_text(moves: list[dict], summary: dict | None = SUMMARY) -> str:
    """Make an answer as a chat screen gives it: with words and a code fence around the JSON."""
    data = {"moves": moves} | ({"summary": summary} if summary is not None else {})
    return f"Here it is.\n```json\n{json.dumps(data, ensure_ascii=False)}\n```\nGood luck!"


def test_good_answer():
    """A complete answer is read, with the move numbers as numbers or texts, and spaces made single."""
    moves = [{"move": 3, **FIELDS}, {"move": "5", **FIELDS, "aim": "line one\nline two"}]
    answer = read_answer(answer_text(moves), [3, 5])
    assert answer.ok and answer.problems == ()
    assert answer.moves[3] == FIELDS and answer.moves[5]["aim"] == "line one line two"
    assert answer.summary == SUMMARY


def test_errors():
    """No JSON, a missing move, or no review are errors."""
    assert [p.kind for p in read_answer("Sorry, I cannot.", [3]).problems] == [PROBLEM_NOT_JSON]
    assert [p.kind for p in read_answer("{broken", [3]).problems] == [PROBLEM_NOT_JSON]
    answer = read_answer(answer_text([{"move": 3, **FIELDS}], None), [3, 5])
    assert not answer.ok
    assert [(p.kind, p.move) for p in answer.problems] == [(PROBLEM_MISSING_MOVE, 5), (PROBLEM_NO_SUMMARY, 0)]


def test_warnings():
    """A move not asked, an empty field and an unknown category are warnings: the answer can still be written."""
    moves = [{"move": 3, **FIELDS, "lesson": "", "category": "その他"}, {"move": 9, **FIELDS}]
    answer = read_answer(answer_text(moves), [3])
    assert answer.ok and set(answer.moves) == {3}
    kinds = [(p.kind, p.move, p.field) for p in answer.problems]
    assert kinds == [
        (PROBLEM_EMPTY_FIELD, 3, "lesson"),
        (PROBLEM_UNKNOWN_CATEGORY, 3, ""),
        (PROBLEM_UNKNOWN_MOVE, 9, ""),
    ]


def test_extract_json():
    """The JSON object is taken out of the words around it."""
    assert extract_json('ok {"a": {"b": 1}} done') == {"a": {"b": 1}}


def test_a_category_in_words_is_read_as_its_name():
    """An AI that writes the category in the words of the prompt gives the same category; others are warned."""
    words = {3: "読み違い", 5: "Wrong direction", 7: "bad luck"}
    moves = [{"move": number, **FIELDS, "category": category} for number, category in words.items()]
    answer = read_answer(answer_text(moves), [3, 5, 7])
    assert [answer.moves[number]["category"] for number in (3, 5, 7)] == ["misread", "wrong_direction", "bad luck"]
    assert [(p.kind, p.move) for p in answer.problems] == [(PROBLEM_UNKNOWN_CATEGORY, 7)]
