"""How the local fight problems are played: the opponent and the score that may be lost (see quiz.fight_judge).

They are kept in the "fights" part of settings.json, next to the review settings of the fights (see app_settings);
the keys of the review settings in the same dict are ignored here.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.quiz.fight_judge import OPPONENT_STRONG, OPPONENTS


@dataclass(frozen=True)
class FightSettings:
    """How the local fight problems are played.

    Attributes:
        opponent: Who plays the opponent's moves, one of quiz.fight_judge.OPPONENTS: KataGo's best moves, or the
            human-like moves of the opponent's rank.
        score_tolerance: How many points the user's score may fall from the start of a fight in a correct answer
            (even the best play loses a little against the best replies).
    """

    opponent: str = OPPONENT_STRONG
    score_tolerance: float = 3.0

    @classmethod
    def from_dict(cls, values: dict) -> FightSettings:
        """Make the settings from the "fights" part of settings.json (missing keys get the default values).

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        default = cls()
        opponent = values.get("opponent", default.opponent)
        if opponent not in OPPONENTS:
            raise ValueError(f"wrong fight setting: opponent must be one of {OPPONENTS}: {opponent!r}")
        tolerance = values.get("score_tolerance", default.score_tolerance)
        if isinstance(tolerance, bool) or not isinstance(tolerance, int | float) or tolerance < 0:
            raise ValueError(f"wrong fight setting: score_tolerance must be a number of 0 or more: {tolerance!r}")
        return cls(opponent=opponent, score_tolerance=float(tolerance))

    def to_dict(self) -> dict:
        """Return the settings as a dict, to be put into the "fights" part of settings.json."""
        return {"opponent": self.opponent, "score_tolerance": self.score_tolerance}
