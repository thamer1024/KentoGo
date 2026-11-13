"""All settings of the quiz, kept in the "quiz" part of settings.json.

The "quiz" part is one flat dict. It has the conditions for choosing problems
(ExtractSettings), the rule for judging answers (ScoringPolicy), and the
settings below that decide how the problems are asked. The review settings are
in the same dict, but are read by review.review_settings, and ignored here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kentogo.mistakes.extract import ExtractSettings
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.limit_offer import LIMITS
from kentogo.quiz.problem_kinds import KIND_ALL, PROBLEM_KINDS
from kentogo.quiz.ratio_offer import WINDOW

# Orders of the problems.
ORDER_FILE_NAME = "file_name"  # By the names of the SGF files.
ORDER_NEWEST = "newest"  # From the SGF file that was changed last.
ORDER_RANDOM = "random"  # All problems mixed.
ORDERS = (ORDER_FILE_NAME, ORDER_NEWEST, ORDER_RANDOM)


@dataclass(frozen=True)
class QuizSettings:
    """The settings of the quiz.

    Attributes:
        games_folder: The folder with the SGF files ("" if it is not set yet).
        order: The order of the problems, one of ORDERS.
        rotate: Rotate and flip the board at random.
        swap_colors: Swap black and white at random.
        extract: Conditions for choosing problems.
        scoring: The rule for judging answers.
        problem_kind: Which problems are asked, one of quiz.problem_kinds.PROBLEM_KINDS.
        ratio_offer: Offer to raise or lower the pass ratio to suit the latest answers (see quiz.ratio_offer).
        ratio_asked_at: How many judged answers there were when the offer was last answered (0 if
            never), so that it is asked again only after enough new answers. It is changed only by
            the offer, not on the settings screen.
        limit_asked_at: The same for the offer of the limit of a correct answer's loss (see quiz.limit_offer),
            which is turned on with ratio_offer too.
        offer_window: How many of the latest answers the offers are made from, and how many new answers are
            needed before they are asked again (1 or more).
        limit_steps: The limits of a correct answer's loss offered one after another, the biggest first
            (empty: the limit is not offered).
    """

    games_folder: str = ""
    order: str = ORDER_FILE_NAME
    rotate: bool = False
    swap_colors: bool = False
    extract: ExtractSettings = field(default_factory=ExtractSettings)
    scoring: ScoringPolicy = field(default_factory=ScoringPolicy)
    ratio_offer: bool = True
    ratio_asked_at: int = 0
    limit_asked_at: int = 0
    offer_window: int = WINDOW
    limit_steps: tuple[float, ...] = LIMITS
    problem_kind: str = KIND_ALL

    @classmethod
    def from_dict(cls, values: dict) -> QuizSettings:
        """Make the settings from the "quiz" part of settings.json.

        Args:
            values: The values. Missing keys get the default values, and unknown keys are ignored.

        Returns:
            The settings.

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        default = cls()
        order = values.get("order", default.order)
        if order not in ORDERS:
            raise ValueError(f"wrong quiz setting: order must be one of {ORDERS}: {order!r}")
        problem_kind = values.get("problem_kind", default.problem_kind)
        if problem_kind not in PROBLEM_KINDS:
            raise ValueError(f"wrong quiz setting: problem_kind must be one of {PROBLEM_KINDS}: {problem_kind!r}")
        games_folder = values.get("games_folder", default.games_folder)
        if not isinstance(games_folder, str):
            raise ValueError(f"wrong quiz setting: games_folder must be a text: {games_folder!r}")
        return cls(
            games_folder=games_folder,
            order=order,
            rotate=_boolean(values, "rotate", default.rotate),
            swap_colors=_boolean(values, "swap_colors", default.swap_colors),
            extract=ExtractSettings.from_dict(values),
            scoring=ScoringPolicy.from_dict(values),
            ratio_offer=_boolean(values, "ratio_offer", default.ratio_offer),
            ratio_asked_at=_count(values, "ratio_asked_at", default.ratio_asked_at),
            limit_asked_at=_count(values, "limit_asked_at", default.limit_asked_at),
            offer_window=_window(values, default.offer_window),
            limit_steps=_limits(values.get("limit_steps", default.limit_steps)),
            problem_kind=problem_kind,
        )

    def to_dict(self) -> dict:
        """Return the settings as one flat dict for the "quiz" part of settings.json."""
        return {
            "games_folder": self.games_folder,
            "order": self.order,
            "rotate": self.rotate,
            "swap_colors": self.swap_colors,
            **self.extract.to_dict(),
            **self.scoring.to_dict(),
            "ratio_offer": self.ratio_offer,
            "ratio_asked_at": self.ratio_asked_at,
            "limit_asked_at": self.limit_asked_at,
            "offer_window": self.offer_window,
            "limit_steps": list(self.limit_steps),
            "problem_kind": self.problem_kind,
        }


def _count(values: dict, key: str, default: int) -> int:
    """Read a whole number that is not negative."""
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"wrong quiz setting: {key} must be a whole number of 0 or more: {value!r}")
    return value


def _window(values: dict, default: int) -> int:
    """Read offer_window: a whole number of 1 or more."""
    value = _count(values, "offer_window", default)
    if value < 1:
        raise ValueError(f"wrong quiz setting: offer_window must be 1 or more: {value!r}")
    return value


def _limits(value: object) -> tuple[float, ...]:
    """Read limit_steps: positive numbers, returned the biggest first without repeats."""
    if not isinstance(value, (list, tuple)) or any(isinstance(item, bool) for item in value):
        raise ValueError(f"wrong quiz setting: limit_steps must be a list of numbers: {value!r}")
    try:
        limits = {float(item) for item in value}
    except (TypeError, ValueError) as error:
        raise ValueError(f"wrong quiz setting: limit_steps must be a list of numbers: {value!r}") from error
    if any(not limit > 0 for limit in limits):
        raise ValueError(f"wrong quiz setting: limit_steps must be positive numbers: {value!r}")
    return tuple(sorted(limits, reverse=True))


def _boolean(values: dict, key: str, default: bool) -> bool:
    """Read a true/false value, and refuse other types (a text "false" would count as true in Python)."""
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"wrong quiz setting: {key} must be true or false: {value!r}")
    return value
