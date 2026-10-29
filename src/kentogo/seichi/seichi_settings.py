"""Settings of the territory counting practice (seichi), kept in the "seichi" part of settings.json.

Besides turning the practice on, they decide which games are counted and in what
order, in the same way as the settings of the quiz: the order of the games, which
come first (games never counted, or games counted badly before), how games counted
badly are asked again, and how many games are counted in one start of the app.

One more value is only in settings.json (not on the settings screen): how long a stone
takes to move when the steps of the computer's seichi are shown.

The keys start with "seichi_", so that they are not mixed up with the quiz settings of
the same kind on the settings screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.repetition.modes import PRIORITIES, PRIORITY_NEW, REVIEW_CURVE, REVIEW_MODES, REVIEW_ONCE

# Orders of the games (the same values as the orders of the quiz problems).
ORDER_FILE_NAME = "file_name"  # By the names of the SGF files.
ORDER_NEWEST = "newest"  # From the SGF file that was changed last.
ORDER_RANDOM = "random"  # Mixed.
ORDERS = (ORDER_FILE_NAME, ORDER_NEWEST, ORDER_RANDOM)

STEP_SECONDS = 0.2  # The default time of the move of a stone in the steps of the computer's seichi.


@dataclass(frozen=True)
class SeichiSettings:
    """The settings of the territory counting practice.

    Attributes:
        use_seichi: Let the user choose the territory counting practice at the start.
            When it is on, the app asks at every start which practice to do.
        order: The order of the games, one of ORDERS.
        priority: Which games come first, one of review_settings.PRIORITIES
            (games never counted, games to count again, or a mix).
        review_mode: How games counted badly are asked again, one of review_settings.REVIEW_MODES.
        review_streak: With REVIEW_CURVE, how many good counts in a row finish a game
            (0: games are not asked again).
        session_limit: The most games counted in a day (0: no limit). The day ends at midnight
            in the computer's time zone.
        daily_limit_off: True to count without the limit (for tests). It is changed only in settings.json.
        step_seconds: How long a stone takes to move to its point when a step of the computer's
            seichi is shown (0: no animation). It is changed only in settings.json.
    """

    use_seichi: bool = False
    order: str = ORDER_RANDOM
    priority: str = PRIORITY_NEW
    review_mode: str = REVIEW_CURVE
    review_streak: int = 2
    session_limit: int = 3
    step_seconds: float = STEP_SECONDS
    daily_limit_off: bool = False

    @property
    def daily_limit(self) -> int:
        """The most games counted in a day (0: no limit)."""
        return 0 if self.daily_limit_off else self.session_limit

    @property
    def once(self) -> bool:
        """True if a game counted badly is asked again only until it is counted well once."""
        return self.review_mode == REVIEW_ONCE

    @classmethod
    def from_dict(cls, values: dict) -> SeichiSettings:
        """Make the settings from the "seichi" part of settings.json.

        Args:
            values: The values. Missing keys get the default values, and unknown keys are ignored.

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        default = cls()
        use_seichi = values.get("use_seichi", default.use_seichi)
        if not isinstance(use_seichi, bool):
            raise ValueError(f"wrong seichi setting: use_seichi must be true or false: {use_seichi!r}")
        return cls(
            use_seichi=use_seichi,
            order=_choice(values, "seichi_order", default.order, ORDERS),
            priority=_choice(values, "seichi_priority", default.priority, PRIORITIES),
            review_mode=_choice(values, "seichi_review_mode", default.review_mode, REVIEW_MODES),
            review_streak=_count(values, "seichi_review_streak", default.review_streak),
            session_limit=_count(values, "seichi_session_limit", default.session_limit),
            step_seconds=_seconds(values, "seichi_step_seconds", default.step_seconds),
            daily_limit_off=_flag(values, "seichi_daily_limit_off", default.daily_limit_off),
        )

    def to_dict(self) -> dict:
        """Return the settings as a dict for the "seichi" part of settings.json."""
        return {
            "use_seichi": self.use_seichi,
            "seichi_order": self.order,
            "seichi_priority": self.priority,
            "seichi_review_mode": self.review_mode,
            "seichi_review_streak": self.review_streak,
            "seichi_session_limit": self.session_limit,
            "seichi_step_seconds": self.step_seconds,
            "seichi_daily_limit_off": self.daily_limit_off,
        }


def _flag(values: dict, key: str, default: bool) -> bool:
    """Read true or false, and refuse other values."""
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"wrong seichi setting: {key} must be true or false: {value!r}")
    return value


def _choice(values: dict, key: str, default: str, choices: tuple[str, ...]) -> str:
    """Read one of the allowed values, and refuse others."""
    value = values.get(key, default)
    if value not in choices:
        raise ValueError(f"wrong seichi setting: {key} must be one of {choices}: {value!r}")
    return value


def _count(values: dict, key: str, default: int) -> int:
    """Read a whole number of 0 or more, and refuse other values."""
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"wrong seichi setting: {key} must be a whole number of 0 or more: {value!r}")
    return value


def _seconds(values: dict, key: str, default: float) -> float:
    """Read a number of seconds of 0 or more (a whole number is allowed too), and refuse other values."""
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"wrong seichi setting: {key} must be a number of 0 or more: {value!r}")
    return float(value)
