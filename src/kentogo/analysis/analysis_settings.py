"""Settings of the analysis of games, kept in the "analysis" part of settings.json.

KentoGo analyzes games in the same way as KaTrain, so the settings are KaTrain's own
(katrain/core/game.py, analyze_extra and write_sgf, KaTrain 1.20.0), and their default
values are copied from KaTrain's config.json when the settings file is made (see from_katrain):

- Every move is analyzed first, as when KaTrain opens a game: with the engine's max_visits
  (or fast_visits, when fast is on, as KaTrain's "load_fast_analysis"), at most max_time seconds each.
- Then, when reanalyze is on, the game is analyzed again as with KaTrain's "Re-analyze game":
  only the mistakes (mistakes_only: moves that lost more than the fourth threshold from the end
  of eval_thresholds) and only the moves from move_from to move_to (0 means the whole game).
- The comments are written as KaTrain writes them: for the classes of mistakes chosen by
  save_feedback (the classes come from eval_thresholds), also for the AI's moves when
  eval_show_ai is on, with the marks of the best moves when save_marks is on, in KaTrain's language.

The analysis data (the KT property) is always written: KentoGo needs it, so it is not a setting.
katrain_compatible chooses KaTrain's behavior as it is (the default; the check box "KaTrain compatible"
on the settings screen later). KentoGo's own mode fixes some of KaTrain's problems (see analysis.rules)
and uses two more settings: reanalyze_threshold and retries.
The visits of the engine (max_visits) are the engine settings (see katago.engine_settings).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# KaTrain's default thresholds of the classes of mistakes (points lost), and which classes get comments.
KATRAIN_THRESHOLDS = (12.0, 6.0, 3.0, 1.5, 0.5, 0.0)
KATRAIN_FEEDBACK = (True, True, True, True, False, False)
MISTAKE_CLASS = 4  # The fourth threshold from the end is KaTrain's limit of a mistake (3 points by default).


@dataclass(frozen=True)
class AnalysisSettings:
    """The settings of the analysis of games.

    Attributes:
        games_folder: The folder of the games to analyze ("" means the games folder of the quiz).
        backup_folder: Where the games are copied before they are written ("" means "backup" in the games folder).
        fast: Analyze every move with fast_visits first, as KaTrain's "load_fast_analysis".
        fast_visits: The visits of the fast analysis (KaTrain's engine setting).
        max_time: The longest time of the first analysis of one move, in seconds (KaTrain's engine setting).
        reanalyze: Analyze the game again, as KaTrain's "Re-analyze game".
        reanalyze_visits: The visits of the second analysis (0 means the visits of the first one
            plus max_visits, as KaTrain).
        mistakes_only: Analyze again only the mistakes (see MISTAKE_CLASS).
        move_from: The first move analyzed again (0 means from the start).
        move_to: The last move analyzed again (0 means to the end).
        eval_thresholds: The lower ends of the classes of mistakes, the biggest first (points lost).
        save_feedback: For each class, whether its moves get a comment.
        eval_show_ai: The AI's moves get comments too.
        save_marks: Mark the best moves in the position before each commented move (KaTrain's MA and SQ).
        language: The language of the comments (KaTrain's language code, such as "en" or "jp").
        katrain_compatible: Analyze and write exactly as KaTrain does.
        reanalyze_threshold: KentoGo's mode: the loss (points) from which a move is analyzed again
            with mistakes_only (KaTrain uses the fourth threshold from the end of eval_thresholds).
        retries: KentoGo's mode: how many times a node that KataGo could not analyze is asked again.
    """

    games_folder: str = ""
    backup_folder: str = ""
    fast: bool = False
    fast_visits: int = 4
    max_time: float = 60.0
    reanalyze: bool = False
    reanalyze_visits: int = 0
    mistakes_only: bool = False
    move_from: int = 0
    move_to: int = 0
    eval_thresholds: tuple[float, ...] = KATRAIN_THRESHOLDS
    save_feedback: tuple[bool, ...] = KATRAIN_FEEDBACK
    eval_show_ai: bool = True
    save_marks: bool = False
    language: str = "en"
    katrain_compatible: bool = True
    reanalyze_threshold: float = 3.0
    retries: int = 2

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
        engine, trainer, general = (_part(config, name) for name in ("engine", "trainer", "general"))
        values = {key: engine[key] for key in ("fast_visits", "max_time") if key in engine}
        values.update(
            {
                key: trainer[key]
                for key in ("eval_thresholds", "save_feedback", "eval_show_ai", "save_marks")
                if key in trainer
            }
        )
        if "load_fast_analysis" in general:
            values["fast"] = general["load_fast_analysis"]
        if "lang" in general:
            values["language"] = general["lang"]
        return cls.from_dict(values)

    def check(self) -> None:
        """Raise ValueError if the values do not go together."""
        if len(self.eval_thresholds) < MISTAKE_CLASS or len(self.eval_thresholds) != len(self.save_feedback):
            raise ValueError("wrong analysis setting: eval_thresholds and save_feedback must have the same length (4+)")
        if list(self.eval_thresholds) != sorted(self.eval_thresholds, reverse=True):
            raise ValueError("wrong analysis setting: eval_thresholds must be the biggest first")
        numbers = {
            "reanalyze_threshold": self.reanalyze_threshold,
            "retries": self.retries,
            "fast_visits": self.fast_visits,
            "max_time": self.max_time,
            "reanalyze_visits": self.reanalyze_visits,
            "move_from": self.move_from,
            "move_to": self.move_to,
        }
        wrong = [name for name, value in numbers.items() if value < 0]
        if wrong:
            raise ValueError(f"wrong analysis setting: {', '.join(wrong)} must not be below 0")
        if self.fast_visits < 1:
            raise ValueError("wrong analysis setting: fast_visits must be 1 or more")

    def mistake_threshold(self) -> float:
        """Return the loss above which a move is a mistake for mistakes_only (as KaTrain)."""
        return self.eval_thresholds[-MISTAKE_CLASS]

    def to_dict(self) -> dict:
        """Return the settings as a dict, for the "analysis" part of settings.json."""
        values = {item.name: getattr(self, item.name) for item in fields(self)}
        return {**values, "eval_thresholds": list(self.eval_thresholds), "save_feedback": list(self.save_feedback)}


def _part(config: dict, name: str) -> dict:
    """Return one part of KaTrain's config.json, or an empty dict."""
    part = config.get(name) if isinstance(config, dict) else None
    return part if isinstance(part, dict) else {}


def _checked(name: str, value: object, default: AnalysisSettings) -> object:
    """Return the value in the type of the default value, or raise ValueError."""
    kind = getattr(default, name)
    if isinstance(kind, tuple):
        return _checked_list(name, value, type(kind[0]))
    return _checked_single(name, value, type(kind))


def _checked_list(name: str, value: object, kind: type) -> tuple:
    """Return a list of values (numbers or booleans) as a tuple, or raise ValueError."""
    if not isinstance(value, list | tuple):
        raise ValueError(f"wrong analysis setting: {name} must be a list: {value!r}")
    return tuple(_checked_single(name, item, kind) for item in value)


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
