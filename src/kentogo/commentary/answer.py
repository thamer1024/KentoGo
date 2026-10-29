"""Read the AI's answer: the JSON asked for in commentary.prompt.answer_format.

The answer is read leniently, because chat screens often add words around it: the JSON
object is taken out of code fences ("```json ... ```") and sentences before and after it.
Then it is checked against the moves that were asked:

- Errors (nothing is written to the SGF file): the text has no JSON object, a move that
  was asked is missing, or there is no review of the whole game.
- Warnings (the answer can still be written): a move that was not asked (it is not used),
  an empty or missing field (it is left empty), or a category that is not one of CATEGORIES.

The category is kept as one of CATEGORIES (an English name). An AI that answers with the
name in words of the prompt (such as 読み違い) instead is understood too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from kentogo.commentary.language import CATEGORIES
from kentogo.commentary.prompt_words import category_by_name

MOVE_FIELDS = ("situation", "category", "what_happened", "aim", "lesson")
SUMMARY_FIELDS = ("category_counts", "main_issue", "next_focus", "loss_comparison")

PROBLEM_NOT_JSON = "not_json"  # Error: no JSON object could be read (detail has the reason).
PROBLEM_MISSING_MOVE = "missing_move"  # Error: a move that was asked is not in the answer.
PROBLEM_NO_SUMMARY = "no_summary"  # Error: there is no review of the whole game.
PROBLEM_UNKNOWN_MOVE = "unknown_move"  # Warning: a move that was not asked (not used).
PROBLEM_EMPTY_FIELD = "empty_field"  # Warning: a field is missing or empty.
PROBLEM_UNKNOWN_CATEGORY = "unknown_category"  # Warning: the category is not one of CATEGORIES.
ERRORS = (PROBLEM_NOT_JSON, PROBLEM_MISSING_MOVE, PROBLEM_NO_SUMMARY)


@dataclass(frozen=True)
class AnswerProblem:
    """A problem found in the answer (the screen chooses the words).

    Attributes:
        kind: One of the PROBLEM_ constants.
        move: The move number it is about (0 if none).
        field: The field it is about ("" if none).
        detail: More information, such as the error of the JSON reader ("" if none).
    """

    kind: str
    move: int = 0
    field: str = ""
    detail: str = ""

    @property
    def is_error(self) -> bool:
        """True if the answer cannot be written to the SGF file because of this problem."""
        return self.kind in ERRORS


@dataclass(frozen=True)
class Answer:
    """The AI's answer, read and checked.

    Attributes:
        moves: The commentary of each move that was asked, by move number: a dict from MOVE_FIELDS to text.
        summary: The review of the whole game: a dict from SUMMARY_FIELDS to text (empty if there is none).
        problems: The problems found, errors and warnings.
    """

    moves: dict[int, dict[str, str]]
    summary: dict[str, str]
    problems: tuple[AnswerProblem, ...]

    @property
    def ok(self) -> bool:
        """True if the answer has no errors, so that it can be written to the SGF file."""
        return not any(problem.is_error for problem in self.problems)


def read_answer(text: str, asked_moves: list[int]) -> Answer:
    """Read and check the AI's answer.

    Args:
        text: The answer as the AI gave it.
        asked_moves: The numbers of the moves that were asked.

    Returns:
        The answer with its problems.
    """
    try:
        data = extract_json(text)
    except ValueError as error:
        return Answer({}, {}, (AnswerProblem(PROBLEM_NOT_JSON, detail=str(error)),))
    problems: list[AnswerProblem] = []
    moves = _read_moves(data.get("moves"), set(asked_moves), problems)
    problems += [AnswerProblem(PROBLEM_MISSING_MOVE, move=number) for number in sorted(set(asked_moves) - set(moves))]
    summary = _read_summary(data.get("summary"), problems)
    return Answer(moves, summary, tuple(problems))


def extract_json(text: str) -> dict:
    """Take the JSON object out of a text, ignoring code fences and words around it.

    Raises:
        ValueError: If there is no JSON object in the text.
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise ValueError(str(error)) from error
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def _read_moves(items: object, asked: set[int], problems: list[AnswerProblem]) -> dict[int, dict[str, str]]:
    """Read the list of moves. Moves that were not asked are told and left out."""
    moves: dict[int, dict[str, str]] = {}
    for item in items if isinstance(items, list) else []:
        number = _move_number(item)
        if number is None:
            continue
        if number not in asked:
            problems.append(AnswerProblem(PROBLEM_UNKNOWN_MOVE, move=number))
            continue
        moves[number] = _fields(item, MOVE_FIELDS, number, problems)
        moves[number]["category"] = _category(moves[number]["category"])
        if moves[number]["category"] and moves[number]["category"] not in CATEGORIES:
            problems.append(AnswerProblem(PROBLEM_UNKNOWN_CATEGORY, move=number, detail=moves[number]["category"]))
    return moves


def _category(value: str) -> str:
    """Return the category as one of CATEGORIES when it is one, or its name in words; otherwise the value itself."""
    if value in CATEGORIES:
        return value
    names = category_by_name()
    return names.get(value, names.get(value.lower(), value))


def _read_summary(item: object, problems: list[AnswerProblem]) -> dict[str, str]:
    """Read the review of the whole game (an error if it is missing or all empty)."""
    if not isinstance(item, dict):
        problems.append(AnswerProblem(PROBLEM_NO_SUMMARY))
        return {}
    summary = _fields(item, SUMMARY_FIELDS, 0, problems)
    if not any(summary.values()):
        problems.append(AnswerProblem(PROBLEM_NO_SUMMARY))
        return {}
    return summary


def _move_number(item: object) -> int | None:
    """Return the move number of an item of the list of moves, or None if it has none."""
    if not isinstance(item, dict):
        return None
    try:
        return int(item.get("move"))
    except (TypeError, ValueError):
        return None


def _fields(item: dict, names: tuple[str, ...], move: int, problems: list[AnswerProblem]) -> dict[str, str]:
    """Return the text of each field (an empty or missing field is "" and is told)."""
    fields = {}
    for name in names:
        value = item.get(name)
        fields[name] = " ".join(str(value).split()) if isinstance(value, str | int | float) else ""
        if not fields[name]:
            problems.append(AnswerProblem(PROBLEM_EMPTY_FIELD, move=move, field=name))
    return fields
