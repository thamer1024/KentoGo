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
from kentogo.quiz.problem_kinds import KIND_ALL, PROBLEM_KINDS

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
    """

    games_folder: str = ""
    order: str = ORDER_FILE_NAME
    rotate: bool = False
    swap_colors: bool = False
    extract: ExtractSettings = field(default_factory=ExtractSettings)
    scoring: ScoringPolicy = field(default_factory=ScoringPolicy)
    ratio_offer: bool = True
    ratio_asked_at: int = 0
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
            "problem_kind": self.problem_kind,
        }


def _count(values: dict, key: str, default: int) -> int:
    """Read a whole number that is not negative."""
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"wrong quiz setting: {key} must be a whole number of 0 or more: {value!r}")
    return value


def _boolean(values: dict, key: str, default: bool) -> bool:
    """Read a true/false value, and refuse other types (a text "false" would count as true in Python)."""
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"wrong quiz setting: {key} must be true or false: {value!r}")
    return value
