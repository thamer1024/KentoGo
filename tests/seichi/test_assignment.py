"""Tests for kentogo.seichi.assignment."""

import itertools
import random

import pytest

from kentogo.seichi.assignment import cheapest_pairs


def test_the_lowest_total_is_found():
    """On small tables, the pairs give the same total as trying every way."""
    rng = random.Random(7)
    for size in range(1, 7):
        for _ in range(30):
            cost = [[rng.randrange(20) for _ in range(size)] for _ in range(size)]
            best = min(sum(cost[row][p[row]] for row in range(size)) for p in itertools.permutations(range(size)))
            pairs = cheapest_pairs(cost)
            assert sorted(pairs) == list(range(size))
            assert sum(cost[row][pairs[row]] for row in range(size)) == best


def test_an_empty_table_and_a_wrong_table():
    """No rows gives no pairs; a table that is not square is refused."""
    assert cheapest_pairs([]) == []
    with pytest.raises(ValueError):
        cheapest_pairs([[1, 2]])
