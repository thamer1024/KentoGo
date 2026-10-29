"""The AI commentary in the comment of a move, in the same form as the user's commentary script.

The script (sgf_commentator_gui.py) writes the commentary before the comment that was
there (the user's notes and KaTrain's text), with a header line and KaTrain's separator:

    <header>
    <commentary>
    <SEPARATOR>
    <the comment that was there>

The header tells the kind of commentary: AI_HEADER on the user's moves, and REVIEW_HEADER
(a review of the whole game) on the last move. A commentary written in another language
than Japanese has the English headers instead (AI_HEADER_EN and REVIEW_HEADER_EN); both
are found. Older versions of the script used OLD_AI_HEADERS. KaTrain keeps the commentary when it loads the file again, because it has
no marker (see record.katrain_comment).

When the last move is also one of the explained moves, KentoGo writes both: the commentary
on the move first, then the review, each with its header.

KaTrain joins the parts without a marker when it saves the file again, so the separators
between the commentary, the review and the user's notes can be lost. A review header at
the start of a line inside the commentary is therefore also found.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.record.katrain_comment import SEPARATOR

AI_HEADER = "--- 【AI指導の解説】 ---"
AI_HEADER_EN = "--- 【AI's View】 ---"
OLD_AI_HEADERS = (
    "--- 【AI指導プロの解説（予想手順の解説付き）】 ---",
    "--- 【AI指導プロの解説(予想手順の解説付き)】 ---",
)
REVIEW_HEADER = "=====================\n★ 棋譜全体の総評・今後のアドバイス ★\n====================="
REVIEW_HEADER_EN = "=====================\n★ AI's Review and Advice ★\n====================="

MOVE_HEADERS = (AI_HEADER, AI_HEADER_EN, *OLD_AI_HEADERS)
REVIEW_HEADERS = (REVIEW_HEADER, REVIEW_HEADER_EN)
_BREAK = f"\n{SEPARATOR}\n"


@dataclass(frozen=True)
class AiComment:
    """A comment split into the AI commentary, the AI review, and the rest.

    Attributes:
        move_text: The commentary on the move without its header ("" if there is none).
        review_text: The review of the whole game without its header ("" if there is none).
        rest: The comment that was there before the commentary was written (the whole
            comment if there is no commentary).
    """

    move_text: str
    review_text: str
    rest: str

    @property
    def has_ai(self) -> bool:
        """True if the comment has a commentary or a review."""
        return bool(self.move_text or self.review_text)


def split_ai_comment(comment: str) -> AiComment:
    """Split the comment of a move into the AI commentary, the AI review, and the rest.

    Args:
        comment: The C property of the node.

    Returns:
        The parts.
    """
    move_text, review_text = "", ""
    rest = comment
    while True:
        header = next((h for h in (*MOVE_HEADERS, *REVIEW_HEADERS) if rest.startswith(h)), None)
        if header is None:
            return AiComment(move_text, review_text, rest)
        text, rest = _cut(rest[len(header) :])
        if header in REVIEW_HEADERS:
            review_text = text
        else:
            move_text, inner_review = _split_inner_review(text)
            review_text = review_text or inner_review


def has_ai_comment(comment: str) -> bool:
    """Return True if the comment of a move starts with an AI commentary or review."""
    return split_ai_comment(comment).has_ai


def compose_comment(
    rest: str,
    move_text: str = "",
    review_text: str = "",
    move_header: str = AI_HEADER,
    review_header: str = REVIEW_HEADER,
) -> str:
    """Make the comment of a move with an AI commentary and/or review before the comment that was there.

    Args:
        rest: The comment without AI parts (see split_ai_comment).
        move_text: The commentary on the move ("" for none).
        review_text: The review of the whole game ("" for none).
        move_header: The header of the commentary (one of MOVE_HEADERS).
        review_header: The header of the review (one of REVIEW_HEADERS).

    Returns:
        The new comment (the same as rest if there is neither a commentary nor a review).
    """
    parts = []
    if move_text:
        parts.append(f"{move_header}\n{move_text}")
    if review_text:
        parts.append(f"{review_header}\n{review_text}")
    if rest:
        parts.append(rest)
    return _BREAK.join(parts)


def _cut(body: str) -> tuple[str, str]:
    """Split the text after a header at the first separator: (the AI text, the rest)."""
    index = body.find(_BREAK)
    if index < 0:
        return body.strip(), ""
    return body[:index].strip(), body[index + len(_BREAK) :]


def _split_inner_review(text: str) -> tuple[str, str]:
    """Split a review that KaTrain joined to the commentary without a separator: (commentary, review)."""
    for header in REVIEW_HEADERS:
        index = text.find("\n" + header)
        if index >= 0:
            return text[:index].strip(), text[index + 1 + len(header) :].strip()
    return text, ""
