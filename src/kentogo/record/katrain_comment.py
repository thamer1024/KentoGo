"""Read the comments that KaTrain writes into SGF files.

A KaTrain comment on a move has two kinds of text:

- Notes written by the user (or by other tools, such as Claude's
  explanations). KaTrain keeps these when it loads the file again.
- Text that KaTrain generates automatically (score, point loss,
  best move, and so on). Each generated part ends with a special
  marker, and KaTrain throws it away and makes it again on load.

The notes come first. Parts are joined with a separator string.

The generated text is written in the language that the user selected
in KaTrain, so it is read by comparing it with the texts of all languages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from kentogo.record.katrain_texts import KATRAIN_TEXTS

# KaTrain puts this marker at the end of every text it generates.
INTERNAL_MARKER = "ㅤ​"

# KaTrain puts this separator between the notes and the generated text.
SEPARATOR = "ㅤㅤ"


def split_comment(comment: str) -> tuple[str, list[str]]:
    """Split a comment into the user's notes and KaTrain's generated parts.

    Args:
        comment: The text of the C property of one SGF node.

    Returns:
        A tuple (notes, generated_parts).
        notes is the user's text, with spaces and new lines at both ends removed.
        generated_parts is a list of the texts that KaTrain generated.
        The marker is removed from each part, and empty parts are dropped.
    """
    notes = []
    generated = []
    for part in comment.split(SEPARATOR):
        if not part.strip():
            continue
        if INTERNAL_MARKER in part:
            generated.append(part.replace(INTERNAL_MARKER, "").strip())
        else:
            notes.append(part)
    return "".join(notes).strip(), generated


# A move in GTP coordinates, such as "Q16", "AB12" (large boards) or "pass".
_GTP_MOVE = r"(?:pass|[A-Z]{1,2}\d{1,2})"

# Regular expressions for the values that KaTrain puts into its texts.
# Some languages write other letters right after a value (for example,
# Korean writes "{top_move}입니다"), so each value has a strict pattern.
_VALUE_PATTERNS = {
    "number": r"(?P<number>\d+)",
    "points_lost": r"(?P<points_lost>-?\d+\.\d+)",
    "pv": r"(?P<pv>[BW]" + _GTP_MOVE + r"(?: " + _GTP_MOVE + r")*)",
    "top_move": r"(?P<top_move>" + _GTP_MOVE + r")",
    "score": r"(?P<score>.*?)",
}


@dataclass(frozen=True)
class KatrainMoveInfo:
    """The evaluation of one move, read from KaTrain's generated text.

    Moves are written as GTP coordinates, such as "Q16" or "pass".

    Attributes:
        language: Language code of the text, such as "jp" or "en".
        move_number: The move number shown by KaTrain.
        color: Color of the player of this move, "B" or "W".
        move: The move that was played.
        points_lost: Points lost by this move. KaTrain writes it only when
            the loss is more than 0.5 points, so it is None otherwise.
        best_move: The best move in the position before this move.
            If the played move was the best, this is the played move.
            None if the text does not say.
        pv_color: Color of the first move of pv.
        pv: KaTrain's predicted sequence from the position before this move.
            It starts with the best move.
        teaching_undo: True if KaTrain took back this move automatically
            in a teaching game.
    """

    language: str
    move_number: int
    color: str
    move: str
    points_lost: float | None
    best_move: str | None
    pv_color: str | None
    pv: tuple[str, ...]
    teaching_undo: bool


@dataclass(frozen=True)
class _LanguagePatterns:
    """Patterns to read the generated text of one language."""

    move: re.Pattern
    points_lost: re.Pattern
    pv: re.Pattern
    top_move: re.Pattern
    best_move: str
    teaching_undo: str


def template_to_regex(template: str) -> str:
    """Turn a KaTrain text template into a regular expression.

    Args:
        template: A text such as "手数{number}" or "推定損失目数：{points_lost:.1f}".

    Returns:
        A regular expression. Each {name} part becomes a named group,
        and the other parts must match exactly. Spaces at both ends of the
        template are removed, because lines are compared after strip().
    """
    regex = ""
    for literal, name in re.findall(r"([^{]*)(?:\{(\w+)(?::[^}]*)?\})?", template.strip()):
        regex += re.escape(literal)
        if name:
            regex += _VALUE_PATTERNS[name]
    return regex


@cache
def _patterns_by_language() -> dict[str, _LanguagePatterns]:
    """Make the patterns for all languages once, and keep them."""
    patterns = {}
    for language, texts in KATRAIN_TEXTS.items():
        # The first line is like "手数169: B H1".
        move = template_to_regex(texts["move"]) + r": (?P<color>[BW]) (?P<move>" + _GTP_MOVE + ")"
        patterns[language] = _LanguagePatterns(
            move=re.compile(move),
            points_lost=re.compile(template_to_regex(texts["Info:point loss"])),
            pv=re.compile(template_to_regex(texts["Info:PV"])),
            top_move=re.compile(template_to_regex(texts["Info:top move"])),
            best_move=texts["Info:best move"].strip(),
            teaching_undo=texts["Info:teaching undo"].strip(),
        )
    return patterns


def parse_pv(text: str) -> tuple[str | None, tuple[str, ...]]:
    """Read a predicted sequence such as "BQ14 M16 N15".

    Args:
        text: The sequence. The first letter is the color of the first move.

    Returns:
        A tuple (color, moves). If the text has no color letter, returns (None, ()).
    """
    tokens = text.split()
    if not tokens or tokens[0][0] not in "BW":
        return None, ()
    return tokens[0][0], (tokens[0][1:], *tokens[1:])


def parse_katrain_text(text: str) -> KatrainMoveInfo | None:
    """Read one part of text that KaTrain generated for a move.

    The language is found from the first line, such as "手数169: B H1".
    The first lines of all languages are different (a test checks this).

    Args:
        text: One generated part, as returned by split_comment.

    Returns:
        The evaluation of the move, or None if the text is not about a move
        (for example, the comment on the first node of the game).
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    for language, patterns in _patterns_by_language().items():
        head = patterns.move.fullmatch(lines[0])
        if head:
            return _read_lines(language, patterns, head, lines[1:])
    return None


def _read_lines(language: str, patterns: _LanguagePatterns, head: re.Match, lines: list[str]) -> KatrainMoveInfo:
    """Read the lines after the first line with the patterns of one language.

    Args:
        language: Language code of the patterns.
        patterns: Patterns of the language.
        head: The match of the first line.
        lines: The lines after the first line, with spaces at both ends removed.

    Returns:
        The evaluation of the move.
    """
    points_lost = None
    best_move = None
    pv_color, pv = None, ()
    teaching_undo = False
    for line in lines:
        if line == patterns.teaching_undo:
            # The lines after this are about the opponent's reply, so stop here.
            teaching_undo = True
            break
        elif match := patterns.points_lost.fullmatch(line):
            points_lost = float(match["points_lost"])
        elif line == patterns.best_move:
            best_move = head["move"]
        elif match := patterns.top_move.fullmatch(line):
            best_move = match["top_move"]
        elif (match := patterns.pv.fullmatch(line)) and not pv:
            pv_color, pv = parse_pv(match["pv"])

    return KatrainMoveInfo(
        language=language,
        move_number=int(head["number"]),
        color=head["color"],
        move=head["move"],
        points_lost=points_lost,
        best_move=best_move,
        pv_color=pv_color,
        pv=pv,
        teaching_undo=teaching_undo,
    )


def read_comment(comment: str) -> tuple[str, KatrainMoveInfo | None]:
    """Get the user's notes and KaTrain's evaluation from a whole comment.

    Args:
        comment: The text of the C property of one SGF node.

    Returns:
        A tuple (notes, info). notes is the same as in split_comment.
        info is the evaluation from the first generated part that is about
        a move, or None if there is no such part.
    """
    notes, generated = split_comment(comment)
    for part in generated:
        info = parse_katrain_text(part)
        if info is not None:
            return notes, info
    return notes, None
