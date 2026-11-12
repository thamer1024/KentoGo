"""Tests for kentogo.analysis.policy_ranking (KataGo's policy ranking, as KaTrain orders it)."""

from kentogo.analysis.policy_ranking import policy_ranking
from kentogo.common.types import Move

SIZE = (5, 5)


def test_policy_ranking_keeps_katrains_order_for_equal_values():
    """Equal values stay column by column from the left, each from the bottom, with the pass last."""
    policy = [0.01] * 26
    policy[12], policy[20], policy[25] = 0.5, 0.02, 0.0  # C3 (third row from the top, third column), A1, pass.
    ranking = policy_ranking({"policy": policy}, "B", SIZE)
    assert [move.gtp() for _, move in ranking[:4]] == ["C3", "A1", "A2", "A3"]
    assert ranking[-1] == (0.0, Move("B", None))
    assert policy_ranking({"policy": None}, "B", SIZE) == []
