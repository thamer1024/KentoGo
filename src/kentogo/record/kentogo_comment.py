"""KentoGo's own text in the comment of a node, apart from the user's notes and KaTrain's text.

Older versions of KentoGo wrote their analysis of a move into the comment in their own form (KentoGo no
longer writes comments, see analysis.sgf_writer, but the text is still found in the games), not in KaTrain's (KaTrain's text ends with KaTrain's marker, see record.katrain_comment). It is one
part of the comment, after the user's notes and KaTrain's text, joined with the same separator:

    <the user's notes>
    <SEPARATOR>
    <KaTrain's text, when KaTrain wrote one>
    <SEPARATOR>
    <KENTOGO_HEADER>
    <KentoGo's text>

The part starts with KENTOGO_HEADER, so it is found again (and removed when the game is analyzed
again) without a marker inside the text. split_kentogo_comment takes it out, so that the rest
is read as before (the user's notes and KaTrain's text, see record.katrain_comment.read_comment).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.record.katrain_comment import SEPARATOR

KENTOGO_HEADER = "--- KentoGo ---"


@dataclass(frozen=True)
class KentogoComment:
    """A comment split into KentoGo's text and the rest.

    Attributes:
        text: KentoGo's text without its header ("" if there is none).
        rest: The comment without KentoGo's part (the user's notes and KaTrain's text).
    """

    text: str
    rest: str


def split_kentogo_comment(comment: str) -> KentogoComment:
    """Take KentoGo's part out of a comment (the C property, without the AI commentary).

    Args:
        comment: The comment.

    Returns:
        KentoGo's text and the rest, the other parts joined again with the separator.
    """
    texts, rest = [], []
    for part in comment.split(SEPARATOR):
        stripped = part.strip("\n")
        if stripped.startswith(KENTOGO_HEADER):
            texts.append(stripped[len(KENTOGO_HEADER) :].strip("\n"))
        else:
            rest.append(part)
    return KentogoComment("\n".join(texts), SEPARATOR.join(rest).strip("\n") if texts else comment)


def kentogo_part(text: str) -> str:
    """Return KentoGo's part of a comment for its text (with the header)."""
    return f"{KENTOGO_HEADER}\n{text.strip()}"
