"""Tests for kentogo.common.handicap (the values of a handicap game, counted from the start)."""

from kentogo.common.handicap import from_start


def test_the_lead_is_counted_from_the_start_and_the_winrate_is_not_used():
    """Black led by 18 points at the start: 43 points later is a lead of 25 gained; the winrate is dropped."""
    assert from_start(0.99, 43.0, 18.0) == (None, 25.0)
    assert from_start(0.2, -10.0, 18.0) == (None, -28.0)


def test_unknown_leads():
    """Without either lead, nothing is known."""
    assert from_start(0.9, None, 18.0) == (None, None)
    assert from_start(0.9, 43.0, None) == (None, None)
