"""The recommended numbers of visits for each kind of computer (the "推奨設定" screen).

KataGo reads very different numbers of positions per second on each computer: a GPU is 30 to
100 times faster than a processor alone. The main model is usually KaTrain's own model, an
18-block one, and the comparison model a heavier one, such as the transformer model
kata1-tf3-b11c768 that KataGo uses as its usual model now. So each kind of computer has two
speeds: the 18-block model's (Preset.speed, estimated from published benchmarks, and for a
base M5 measured: about 600 positions per second), and the heavy model's (Preset.compare_speed:
about half of it with CUDA on NVIDIA GPUs, and about a fifth with Metal on a Mac or on a
processor alone).

As for measured speeds (see katago.speed), each analysis takes about 1.6 seconds, so that the
judging and the comparison model (three analyses each) take at most about five seconds each
(with KataGo already loaded: it is started with the app). The territory and the standing need
only a shallow reading, and each of them is two analyses with the owner of every point, so
they get a quarter of the main model's visits. A user who wants deeper or quicker reading
changes the visits on the settings screen. On slow computers the visits would be too few, so
the main model and the comparison model get at least MIN_VISITS (an analysis then takes some
seconds; the screen advises a lighter model there).

The computers with a processor or a GPU come first, from the slowest; the Macs come last, from
the slowest. A Mac's speed depends on the kind of KataGo (the Metal version is much faster than
the others), on the number of GPU cores (base, Pro, Max or Ultra), and on the generation (the
GPU of M5 has its own parts for AI: a base M5 reads about 600 positions per second, faster than
an M1 to M4 Max). So the Macs are named by their speed, with examples of each.

A preset changes only the numbers of visits. The paths of KataGo and its models stay as they are.
When the user does not know the kind of computer, KataGo's speed is measured instead, and the
numbers of visits are made from it (see katago.speed).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from kentogo.katago.engine_settings import EngineSettings

PRESET_CPU_OLD = "cpu_old"  # No GPU, an old processor (Intel Core 4th to 7th, AMD Ryzen 1000 or older).
PRESET_CPU_NEW = "cpu_new"  # No GPU, a newer processor (Intel Core 8th or later, AMD Ryzen 2000 or later).
PRESET_GPU_MIDDLE = "gpu_middle"  # An entry or middle class GPU.
PRESET_GPU_HIGH = "gpu_high"  # A high class GPU.
PRESET_MAC_STANDARD = "mac_standard"  # Not the Metal version of KataGo, or a base M1 or M2.
PRESET_MAC_FAST = "mac_fast"  # The Metal version with a base M3 or M4, or a Pro chip of M1 to M4.
PRESET_MAC_FASTER = "mac_faster"  # The Metal version with a Max or Ultra chip of M1 to M4.
PRESET_MAC_FASTEST = "mac_fastest"  # The Metal version with M5 or later.


@dataclass(frozen=True)
class Preset:
    """The recommended numbers of visits for one kind of computer.

    Attributes:
        key: One of the PRESET_ constants (the screen names it with the text "preset_<key>").
        max_visits: The visits of the main model, for judging answers.
        compare_max_visits: The visits of the comparison model.
        estimate_visits: The visits of the territory and the standing.
        speed: The positions per second of the main model (an 18-block one; estimated).
        compare_speed: The positions per second of the comparison model (a heavy one; estimated).
    """

    key: str
    max_visits: int
    compare_max_visits: int
    estimate_visits: int
    speed: int
    compare_speed: int


MIN_VISITS = 5  # The fewest visits of the main model and the comparison model in a preset.
PC_PRESETS = (
    Preset(PRESET_CPU_OLD, 16, 5, 4, 10, 2),
    Preset(PRESET_CPU_NEW, 40, 8, 10, 25, 5),
    Preset(PRESET_GPU_MIDDLE, 480, 240, 120, 300, 150),
    Preset(PRESET_GPU_HIGH, 1600, 800, 400, 1000, 500),
)
MAC_PRESETS = (
    Preset(PRESET_MAC_STANDARD, 80, 16, 20, 50, 10),
    Preset(PRESET_MAC_FAST, 160, 32, 40, 100, 20),
    Preset(PRESET_MAC_FASTER, 360, 70, 90, 225, 45),
    Preset(PRESET_MAC_FASTEST, 960, 190, 240, 600, 120),
)
PRESETS = (*PC_PRESETS, *MAC_PRESETS)  # In the order of the screen.


def apply_preset(engine: EngineSettings, preset: Preset) -> EngineSettings:
    """Return the engine settings with the numbers of visits of a preset (the other settings are kept)."""
    return replace(
        engine,
        max_visits=preset.max_visits,
        compare_max_visits=preset.compare_max_visits,
        estimate_visits=preset.estimate_visits,
    )
