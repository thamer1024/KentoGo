"""Settings of the analysis of games, kept in the "analysis" part of settings.json.

KentoGo analyzes games in its own way (see analysis.analyze) and writes only what the problems need
(see analysis.sgf_writer). Its fast_visits is KaTrain's own (katrain/core/game.py, KaTrain 1.20.0), and
its default value is copied from KaTrain's config.json when the settings file is made (see from_katrain):

- Every move is analyzed first with fast_visits (KaTrain's fast analysis): this only finds the moves
  that can become problems, which are then read deeply. The positions that cannot become problems are
  never read more than that.
- The moves that can become problems are read more deeply, with deep_visits (see analysis.analyze; which
  moves comes from the quiz settings), at most deep_max_moves of them in a game.
The analysis data (the KGA property) is always written: KentoGo needs it, so it is not a setting.
KentoGo writes no comments and no marks, so KaTrain's settings of them are not here.
A position that KataGo could not analyze is asked again (retries).
No number of visits or seconds is fixed in the code: a strong GPU and a processor alone need very
different numbers, so they come from the settings (these, and the engine's max_visits).
The visits of the engine (max_visits) are the engine settings (see katago.engine_settings).
Old settings files may still have settings that are no longer used: "katrain_compatible", "max_time",
"fast" (the first analysis read every position with the engine's max_visits when it was off), the settings
of the comments ("eval_thresholds", "save_feedback", "eval_show_ai", "save_marks", "language"), of the
analysis again ("reanalyze", "reanalyze_visits", "mistakes_only", "move_from", "move_to",
"reanalyze_threshold") and of KentoGo's own readings ("area_readings", "end_reading", "pass_readings",
"settled_lines", "settle_radius", "settle_change", "settle_step", "settle_max_moves"). Unknown keys are
ignored, and they are gone when the settings are saved again.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class AnalysisSettings:
    """The settings of the analysis of games.

    Attributes:
        games_folder: The folder of the games to analyze ("" means the games folder of the quiz).
        backup_folder: Where the games are copied before they are written ("" means "backup" in the games folder).
        fast_visits: The visits of the first analysis of every position (KaTrain's engine setting); the first
            analysis reads at least katago.presets.MIN_FAST_VISITS (see analysis.analyze.first_visits).
        retries: How many times a node that KataGo could not analyze is asked again.
        deep_visits: The visits of the deep reading of the moves that can become problems
            (0 means the engine's max_visits).
        deep_max_moves: The most moves read deeply in a game, the biggest losses first; the opponent's moves
            take at most half of them (0 means no limit).
    """

    games_folder: str = ""
    backup_folder: str = ""
    fast_visits: int = 4
    retries: int = 2
    deep_visits: int = 0
    deep_max_moves: int = 6

    @classmethod
    def from_dict(cls, values: dict) -> AnalysisSettings:
        """Make the settings from the "analysis" part of settings.json.

        Args:
            values: The values. Missing keys get the default values, and unknown keys are ignored.

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        default = cls()
        kept = {}
        for item in fields(cls):
            kept[item.name] = _checked(item.name, values.get(item.name, getattr(default, item.name)), default)
        settings = cls(**kept)
        settings.check()
        return settings

    @classmethod
    def from_katrain(cls, config: dict) -> AnalysisSettings:
        """Copy the settings of the analysis from KaTrain's config.json (all of it).

        Args:
            config: KaTrain's config.json (see katago.locate.read_katrain_config).

        Raises:
            ValueError: If a value in KaTrain's settings has a wrong type.
        """
        engine = _part(config, "engine")
        values = {key: engine[key] for key in ("fast_visits",) if key in engine}
        return cls.from_dict(values)

    def check(self) -> None:
        """Raise ValueError if the values do not go together."""
        numbers = {
            "retries": self.retries,
            "fast_visits": self.fast_visits,
            "deep_visits": self.deep_visits,
            "deep_max_moves": self.deep_max_moves,
        }
        wrong = [name for name, value in numbers.items() if value < 0]
        if wrong:
            raise ValueError(f"wrong analysis setting: {', '.join(wrong)} must not be below 0")
        if self.fast_visits < 1:
            raise ValueError("wrong analysis setting: fast_visits must be 1 or more")

    def to_dict(self) -> dict:
        """Return the settings as a dict, for the "analysis" part of settings.json."""
        return {item.name: getattr(self, item.name) for item in fields(self)}


def _part(config: dict, name: str) -> dict:
    """Return one part of KaTrain's config.json, or an empty dict."""
    part = config.get(name) if isinstance(config, dict) else None
    return part if isinstance(part, dict) else {}


def _checked(name: str, value: object, default: AnalysisSettings) -> object:
    """Return the value in the type of the default value, or raise ValueError."""
    return _checked_single(name, value, type(getattr(default, name)))


def _checked_single(name: str, value: object, kind: type) -> object:
    """Return one value in its type (an int is taken as a float), or raise ValueError."""
    if kind is bool:
        if isinstance(value, bool):
            return value
    elif kind is float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    elif isinstance(value, kind) and not isinstance(value, bool):
        return value
    raise ValueError(f"wrong analysis setting: {name} must be {kind.__name__}: {value!r}")
