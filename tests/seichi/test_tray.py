"""Tests for kentogo.seichi.tray."""

import pytest

from kentogo.seichi.tray import tray_layout


@pytest.mark.parametrize(
    ("count", "layout"),
    [(0, (0, 0)), (1, (0, 1)), (10, (0, 10)), (11, (1, 1)), (20, (1, 10)), (21, (2, 1)), (35, (3, 5))],
)
def test_tray_layout(count, layout):
    """Single stones are 1 to 10; the rest are groups of ten."""
    assert tray_layout(count) == layout
