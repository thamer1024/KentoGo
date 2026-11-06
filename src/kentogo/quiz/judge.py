"""Decide whether an answer is correct.

The rule has four values in ScoringPolicy, and the user can change them on the
settings screen. They are kept in the "quiz" part of settings.json.

- Small problems (the game move lost less than small_problem_threshold points):
  the answer is correct if it does not lose more than the game move.
- Other problems: the answer is correct if it gets back at least pass_ratio
  of the loss, and (when max_answer_loss is set) loses at most max_answer_loss
  points: in a big problem a ratio alone lets a big mistake pass (70% of 20 points
  still allows an answer that loses 6 points).
- In both cases, the answer is also correct if it loses at most tolerance
  points (it is almost as good as the best move).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.quiz.score import score_answer


@dataclass(frozen=True)
class ScoringPolicy:
    """The rule for deciding whether an answer is correct.

    Attributes:
        small_problem_threshold: A problem is small if the game move lost less than this.
        pass_ratio: For other problems, the part of the loss (0.0 to 1.0) that the
            answer must get back.
        tolerance: An answer that loses at most this many points is always correct.
        max_answer_loss: For other problems, the most points that a correct answer may lose,
            or 0 for no limit.
    """

    small_problem_threshold: float = 3.0
    pass_ratio: float = 0.8
    tolerance: float = 1.0
    max_answer_loss: float = 0.0

    @classmethod
    def from_dict(cls, values: dict) -> ScoringPolicy:
        """Make the rule from a dict read from settings.json.

        Args:
            values: The "quiz" part of the settings. Missing keys get the default values,
                and unknown keys are ignored.

        Returns:
            The rule.

        Raises:
            ValueError: If a value is not a number, pass_ratio is not between 0 and 1, or
                max_answer_loss is negative.
        """
        default = cls()
        try:
            policy = cls(
                small_problem_threshold=float(values.get("small_problem_threshold", default.small_problem_threshold)),
                pass_ratio=float(values.get("pass_ratio", default.pass_ratio)),
                tolerance=float(values.get("tolerance", default.tolerance)),
                max_answer_loss=float(values.get("max_answer_loss", default.max_answer_loss)),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"wrong scoring setting: {error}") from error
        if not 0.0 <= policy.pass_ratio <= 1.0:
            raise ValueError(f"wrong scoring setting: pass_ratio must be between 0 and 1: {policy.pass_ratio}")
        if policy.max_answer_loss < 0:
            raise ValueError(f"wrong scoring setting: max_answer_loss must not be negative: {policy.max_answer_loss}")
        return policy

    def to_dict(self) -> dict:
        """Return the rule as a dict that can be written to settings.json."""
        return {
            "small_problem_threshold": self.small_problem_threshold,
            "pass_ratio": self.pass_ratio,
            "tolerance": self.tolerance,
            "max_answer_loss": self.max_answer_loss,
        }


def judge_small_problem(actual_loss: float, answer_loss: float, policy: ScoringPolicy) -> bool:
    """Judge a small problem: correct if the answer is not worse than the game move, or within the tolerance."""
    return answer_loss <= actual_loss or answer_loss <= policy.tolerance


def judge_by_ratio(actual_loss: float, answer_loss: float, policy: ScoringPolicy) -> bool:
    """Judge a normal problem: correct if the answer gets back enough of the loss without losing more than
    the limit, or is within the tolerance."""
    gets_back = score_answer(actual_loss, answer_loss) >= policy.pass_ratio
    return (gets_back and within_limit(answer_loss, policy)) or answer_loss <= policy.tolerance


def within_limit(answer_loss: float, policy: ScoringPolicy) -> bool:
    """Return True if the answer loses at most max_answer_loss points (always True without a limit)."""
    return policy.max_answer_loss == 0 or answer_loss <= policy.max_answer_loss


def judge_answer(actual_loss: float, answer_loss: float, policy: ScoringPolicy) -> bool:
    """Decide whether an answer is correct, using the rule for small or normal problems.

    Args:
        actual_loss: Points lost by the move in the game.
        answer_loss: Points lost by the answer, calculated under the same conditions.
        policy: The rule.

    Returns:
        True if the answer is correct.
    """
    if actual_loss < policy.small_problem_threshold:
        return judge_small_problem(actual_loss, answer_loss, policy)
    else:
        return judge_by_ratio(actual_loss, answer_loss, policy)
