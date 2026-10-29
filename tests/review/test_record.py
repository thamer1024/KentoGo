"""Tests for kentogo.review.record (the making of records from quiz sessions is tested in test_answers.py)."""

from kentogo.review.record import LOSS_FROM_KATAGO, LOSS_FROM_SGF, LOSS_UNKNOWN, AnswerRecord


def test_record_before_it_is_saved():
    """A record has no record_id until it is saved."""
    record = AnswerRecord("p1", "t", "g.sgf", 3, "B", "Q4", "A19", "Q4", None, None, LOSS_UNKNOWN, None, None, 0, False)
    assert record.record_id is None


def test_loss_sources_are_different():
    """The three sources of losses can be told apart (they are saved as texts)."""
    assert len({LOSS_UNKNOWN, LOSS_FROM_SGF, LOSS_FROM_KATAGO}) == 3
