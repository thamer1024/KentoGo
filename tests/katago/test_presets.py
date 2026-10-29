"""Tests for kentogo.katago.presets."""

import pytest

from kentogo.katago.engine_settings import EngineSettings
from kentogo.katago.presets import MAC_PRESETS, MIN_VISITS, PC_PRESETS, PRESETS, apply_preset


@pytest.mark.parametrize("presets", [PC_PRESETS, MAC_PRESETS], ids=["pc", "mac"])
def test_presets_go_from_the_slowest_computer_to_the_fastest(presets):
    """In each list (the Macs come last), each kind of computer is faster than the one before, with no fewer visits."""
    assert PRESETS[-len(MAC_PRESETS) :] == MAC_PRESETS
    for slower, faster in zip(presets, presets[1:]):
        assert slower.speed < faster.speed
        assert slower.max_visits <= faster.max_visits and slower.estimate_visits <= faster.estimate_visits


def test_presets_keep_the_waiting_short():
    """An analysis takes about 1.6 seconds at the speed of each model (unless the fewest visits are more)."""
    for preset in PRESETS:
        for visits, speed in ((preset.max_visits, preset.speed), (preset.compare_max_visits, preset.compare_speed)):
            assert visits == MIN_VISITS or visits / speed <= 1.7, preset.key
            assert visits >= MIN_VISITS
        assert preset.estimate_visits <= preset.max_visits / 4 + 1, preset.key


def test_a_preset_changes_only_the_visits():
    """The numbers of visits are replaced; the paths and the other settings are kept."""
    engine = EngineSettings(katago="bin/katago", model="m.bin.gz", max_visits=2500, wide_root_noise=0.02)
    changed = apply_preset(engine, PRESETS[0])
    assert (changed.max_visits, changed.compare_max_visits, changed.estimate_visits) == (16, 5, 4)
    assert (changed.katago, changed.model, changed.wide_root_noise) == ("bin/katago", "m.bin.gz", 0.02)


def test_every_preset_has_its_name_and_examples():
    """The screen shows the name and the examples of each kind of computer."""
    from kentogo.gui.texts import TEXTS

    for preset in PRESETS:
        assert f"preset_{preset.key}" in TEXTS and f"preset_{preset.key}_examples" in TEXTS
