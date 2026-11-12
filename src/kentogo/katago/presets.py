"""The recommended numbers of visits for each kind of computer (the "推奨設定" screen).

KataGo reads very different numbers of positions per second on each computer: a GPU is 30 to
100 times faster than a processor alone. The model is usually KaTrain's own model, an 18-block
one, so each kind of computer has the speed of that model (Preset.speed, estimated from published
benchmarks, and for a base M5 measured: about 600 positions per second).

As for measured speeds (see katago.speed), each analysis takes about 1.6 seconds, so that the
judging (three analyses) takes at most about five seconds (with KataGo already loaded: it is
started with the app). The territory and the standing need only a shallow reading, and each of
them is two analyses with the owner of every point, so they get a quarter of the main model's
visits. A user who wants deeper or quicker reading changes the visits on the settings screen.
On slow computers the visits would be too few, so the main model gets at least MIN_VISITS (an
analysis then takes some seconds; the screen advises a lighter model there).

The computers with a processor or a GPU come first, from the slowest; the Macs come last, from
the slowest. A Mac's speed depends on the kind of KataGo (the Metal version is much faster than
the others), on the number of GPU cores (base, Pro, Max or Ultra), and on the generation (the
GPU of M5 has its own parts for AI: a base M5 reads about 600 positions per second, faster than
an M1 to M4 Max). So the Macs are named by their speed, with examples of each.

The analysis of games (see analysis.analyze) should take about GAME_SECONDS for a game, a time that
a person can wait for. The positions that can be read in that time at a computer's speed are shared:
half for the first analysis of every move (about GAME_POSITIONS positions, with the played moves read
again), which only finds the mistakes and is set as KaTrain's fast analysis (fast_visits), and half for
the deep reading of the moves that can become problems (DEEP_POSITIONS positions: the analysis's
deep_max_moves moves, four readings each), which gives their losses. These are analysis settings, and a
preset sets them too. A user who can wait longer sets more visits on the analysis page. On a computer
without a GPU the visits are then few, and the losses less exact; the fewest visits are MIN_FAST_VISITS
and MIN_DEEP_VISITS, so such a computer takes longer than GAME_SECONDS. The first analysis never reads
fewer than MIN_FAST_VISITS, whatever the settings say (see analysis.analyze.first_visits): with fewer,
KataGo's score of a move is too rough to find the mistakes that can become problems.

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
        estimate_visits: The visits of the territory and the standing.
        speed: The positions per second of the main model (an 18-block one; estimated).
        fast_visits: The visits of the first analysis of a game (an analysis setting, see GAME_SECONDS).
        deep_visits: The visits of the deep reading in the analysis of games (an analysis setting).
    """

    key: str
    max_visits: int
    estimate_visits: int
    speed: int
    fast_visits: int
    deep_visits: int


MIN_VISITS = 5  # The fewest visits of the main model in a preset.
DEEP_SHARE = 4  # Before the speed is known, the deep reading reads this many times the main model's visits.
GAME_SECONDS = 120  # The analysis of a game should take about this long (see the module's docstring).
GAME_POSITIONS = 290  # About 250 moves of a game analyzed first, and about 40 played moves read again.
DEEP_POSITIONS = 24  # 6 moves read deeply (the analysis's deep_max_moves), 4 readings each.
FIRST_SHARE = 0.5  # The share of the time of the first analysis; the rest is the deep reading.
MIN_FAST_VISITS = 50  # The fewest visits of the first analysis (fewer cannot find the mistakes reliably).
MIN_DEEP_VISITS = 50  # The fewest visits of the deep reading.


def round_visits(visits: float) -> int:
    """Round a number of visits to two significant digits, such as 739 to 740 or 1234 to 1200."""
    whole = int(visits)
    if whole < 100:
        return whole
    digits = len(str(whole)) - 2
    return round(whole, -digits)


def analysis_visits_for(speed: float) -> tuple[int, int]:
    """Return (fast_visits, deep_visits) that analyze a game in about GAME_SECONDS at a speed (positions per second)."""
    positions = speed * GAME_SECONDS
    fast = max(MIN_FAST_VISITS, round_visits(positions * FIRST_SHARE / GAME_POSITIONS))
    deep = max(MIN_DEEP_VISITS, round_visits(positions * (1 - FIRST_SHARE) / DEEP_POSITIONS))
    return fast, deep


def _preset(key: str, max_visits: int, estimate: int, speed: int) -> Preset:
    """Make a preset; the visits of the analysis of games come from its speed (see analysis_visits_for)."""
    return Preset(key, max_visits, estimate, speed, *analysis_visits_for(speed))


PC_PRESETS = (
    _preset(PRESET_CPU_OLD, 16, 4, 10),
    _preset(PRESET_CPU_NEW, 40, 10, 25),
    _preset(PRESET_GPU_MIDDLE, 480, 120, 300),
    _preset(PRESET_GPU_HIGH, 1600, 400, 1000),
)
MAC_PRESETS = (
    _preset(PRESET_MAC_STANDARD, 80, 20, 50),
    _preset(PRESET_MAC_FAST, 160, 40, 100),
    _preset(PRESET_MAC_FASTER, 360, 90, 225),
    _preset(PRESET_MAC_FASTEST, 960, 240, 600),
)
PRESETS = (*PC_PRESETS, *MAC_PRESETS)  # In the order of the screen.


def deep_visits_for(max_visits: int) -> int:
    """Return the visits of the deep reading before the speed is known (DEEP_SHARE times the main model's visits)."""
    return max(1, max_visits * DEEP_SHARE)


def apply_preset(engine: EngineSettings, preset: Preset) -> EngineSettings:
    """Return the engine settings with the numbers of visits of a preset (the other settings are kept).

    The visits of the analysis of games are analysis settings: the caller sets them (preset.fast_visits as
    KaTrain's fast analysis, and preset.deep_visits).
    """
    return replace(engine, max_visits=preset.max_visits, estimate_visits=preset.estimate_visits)
