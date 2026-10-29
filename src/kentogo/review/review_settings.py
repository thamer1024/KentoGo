"""The settings of reviews and of how many problems are asked.

They are kept in the "quiz" part of settings.json, next to the quiz settings
(the file has looked like this from the start), but they belong to the review
feature, so the quiz feature does not need to know them. Keys of the quiz
settings in the same dict are ignored here.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.repetition.modes import PRIORITIES, PRIORITY_NEW, REVIEW_CURVE, REVIEW_MODES


@dataclass(frozen=True)
class ReviewSettings:
    """The settings of reviews.

    Attributes:
        review_mode: How problems answered wrong are reviewed, one of REVIEW_MODES.
        review_streak: With REVIEW_CURVE, how many correct answers in a row finish the review
            of a problem (0: problems are not asked again).
        priority: Which problems are asked first, one of PRIORITIES.
        session_limit: The most problems asked in a day, reviews included
            (0: no limit). The day ends at midnight in the computer's time zone.
        daily_limit_off: True to ask without the limit (for tests). It is changed only in settings.json.
    """

    review_mode: str = REVIEW_CURVE
    review_streak: int = 2
    priority: str = PRIORITY_NEW
    session_limit: int = 20
    daily_limit_off: bool = False

    @property
    def daily_limit(self) -> int:
        """The most problems asked in a day (0: no limit)."""
        return 0 if self.daily_limit_off else self.session_limit

    @classmethod
    def from_dict(cls, values: dict) -> ReviewSettings:
        """Make the settings from the "quiz" part of settings.json.

        Args:
            values: The values. Missing keys get the default values, and other keys are ignored.

        Returns:
            The settings.

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        default = cls()
        priority = values.get("priority", default.priority)
        if priority not in PRIORITIES:
            raise ValueError(f"wrong review setting: priority must be one of {PRIORITIES}: {priority!r}")
        review_mode = values.get("review_mode", default.review_mode)
        if review_mode not in REVIEW_MODES:
            raise ValueError(f"wrong review setting: review_mode must be one of {REVIEW_MODES}: {review_mode!r}")
        return cls(
            review_mode=review_mode,
            review_streak=_count(values, "review_streak", default.review_streak),
            priority=priority,
            session_limit=_count(values, "session_limit", default.session_limit),
            daily_limit_off=_flag(values, "daily_limit_off", default.daily_limit_off),
        )

    def to_dict(self) -> dict:
        """Return the settings as a dict, to be put into the "quiz" part of settings.json."""
        return {
            "review_mode": self.review_mode,
            "review_streak": self.review_streak,
            "priority": self.priority,
            "session_limit": self.session_limit,
            "daily_limit_off": self.daily_limit_off,
        }


def _flag(values: dict, key: str, default: bool) -> bool:
    """Read true or false, and refuse other values."""
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"wrong review setting: {key} must be true or false: {value!r}")
    return value


def _count(values: dict, key: str, default: int) -> int:
    """Read a whole number of 0 or more, and refuse other values."""
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"wrong review setting: {key} must be a whole number of 0 or more: {value!r}")
    return value
