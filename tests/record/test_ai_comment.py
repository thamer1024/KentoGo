"""Tests for kentogo.record.ai_comment."""

from kentogo.record.ai_comment import (
    AI_HEADER,
    OLD_AI_HEADERS,
    REVIEW_HEADER,
    AiComment,
    compose_comment,
    has_ai_comment,
    split_ai_comment,
)
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR

KATRAIN = f"\nMove 3: B A19\nEstimated point loss: 8.0\nPV: BQ4\n{INTERNAL_MARKER}"


def test_split_move_commentary():
    """The commentary is split from the comment that was there, as the script writes it."""
    comment = f"{AI_HEADER}\nA slow move.\nPlay Q4.\n{SEPARATOR}\nmy note{SEPARATOR}{KATRAIN}"
    assert split_ai_comment(comment) == AiComment("A slow move.\nPlay Q4.", "", f"my note{SEPARATOR}{KATRAIN}")


def test_split_review_and_old_headers():
    """The review and the commentary with an older header are found too."""
    review = f"{REVIEW_HEADER}\nWell played.\n{SEPARATOR}\n{KATRAIN}"
    assert split_ai_comment(review) == AiComment("", "Well played.", KATRAIN)
    assert split_ai_comment(f"{OLD_AI_HEADERS[1]}\nOld text.") == AiComment("Old text.", "", "")


def test_commentary_and_review_on_one_move():
    """The last move can have both, the commentary first. Composing and splitting give the same parts."""
    comment = compose_comment(KATRAIN, "On the move.", "On the game.")
    assert comment == f"{AI_HEADER}\nOn the move.\n{SEPARATOR}\n{REVIEW_HEADER}\nOn the game.\n{SEPARATOR}\n{KATRAIN}"
    assert split_ai_comment(comment) == AiComment("On the move.", "On the game.", KATRAIN)


def test_parts_joined_by_katrain():
    """After KaTrain saves the file again, the separator between the commentary and the review is gone."""
    joined = f"{AI_HEADER}\nOn the move.\n\n{REVIEW_HEADER}\nOn the game.\n{SEPARATOR}{KATRAIN}"
    parts = split_ai_comment(joined)
    assert (parts.move_text, parts.review_text) == ("On the move.", "On the game.")


def test_comment_without_commentary():
    """A comment without a header is all kept as the rest, and composing nothing keeps it."""
    comment = f"my note{SEPARATOR}{KATRAIN}"
    assert split_ai_comment(comment) == AiComment("", "", comment)
    assert not has_ai_comment(comment) and has_ai_comment(f"{AI_HEADER}\ntext")
    assert compose_comment(comment) == comment and compose_comment("") == ""


def test_english_headers_are_found_and_written():
    """A commentary written with the English headers is split as one with the Japanese headers."""
    from kentogo.record.ai_comment import AI_HEADER_EN, REVIEW_HEADER_EN

    comment = compose_comment(KATRAIN, "On the move.", "On the game.", AI_HEADER_EN, REVIEW_HEADER_EN)
    assert (
        comment
        == f"{AI_HEADER_EN}\nOn the move.\n{SEPARATOR}\n{REVIEW_HEADER_EN}\nOn the game.\n{SEPARATOR}\n{KATRAIN}"
    )
    assert split_ai_comment(comment) == AiComment("On the move.", "On the game.", KATRAIN)
    joined = f"{AI_HEADER_EN}\nOn the move.\n\n{REVIEW_HEADER_EN}\nOn the game.\n{SEPARATOR}{KATRAIN}"
    assert split_ai_comment(joined).review_text.startswith("On the game.")
