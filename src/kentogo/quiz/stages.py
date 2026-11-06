"""Staged problems: the problems with the biggest losses first, then smaller ones (段階出題).

The stages are thresholds of the points lost, the biggest first (for example 20, 10, 5, 3). A
stage is cleared when every problem that lost at least its threshold has been answered correctly
at least once (problems set aside count as answered). The current stage is the first one that is
not cleared; new problems that lost less than its threshold are not asked yet. Reviews are not
affected. When every stage is cleared, the last (smallest) threshold is used.

Nothing is saved: the stage is worked out from the history each time, so a new game with a big
mistake brings a bigger stage back until its problems are answered correctly.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Protocol


class HasLoss(Protocol):
    """A problem with an ID and the points lost by the game move. Nothing else is needed."""

    problem_id: str
    points_lost: float


@dataclass(frozen=True)
class StageStatus:
    """Where the user is in the stages.

    Attributes:
        threshold: The threshold of the current stage, or None if the stages are not used.
        index: The number of the current stage, from 0.
        count: How many stages there are (0 if they are not used).
        left: How many problems of the current stage are not answered correctly yet.
    """

    threshold: float | None
    index: int = 0
    count: int = 0
    left: int = 0


NO_STAGES = StageStatus(None)


def parse_stages(text: str) -> tuple[float, ...]:
    """Return the thresholds from a text such as "20,10,5,3", the biggest first, without repeats.

    An empty text gives () (the stages are not used).

    Raises:
        ValueError: If a value is not a positive number.
    """
    values = []
    for part in text.replace("、", ",").split(","):
        if not part.strip():
            continue
        value = float(part)
        if not value > 0:
            raise ValueError(f"a stage must be a positive number of points: {part.strip()!r}")
        values.append(value)
    return tuple(sorted(set(values), reverse=True))


def current_stage(problems: Iterable[HasLoss], answered: Collection[str], stages: tuple[float, ...]) -> StageStatus:
    """Return the current stage.

    Args:
        problems: All problems (the same ID more than once counts once).
        answered: The IDs of the problems answered correctly at least once, and of those set aside.
        stages: The thresholds, the biggest first (see parse_stages).
    """
    if not stages:
        return NO_STAGES
    losses = {problem.problem_id: problem.points_lost for problem in problems}
    for index, threshold in enumerate(stages):
        left = sum(1 for problem_id, loss in losses.items() if loss >= threshold and problem_id not in answered)
        if left > 0:
            return StageStatus(threshold, index, len(stages), left)
    return StageStatus(stages[-1], len(stages) - 1, len(stages), 0)


def held_back(problems: Iterable[HasLoss], new_ids: Collection[str], status: StageStatus) -> set[str]:
    """Return the IDs of the new problems that are not asked in the current stage (they lost less).

    Args:
        problems: All problems.
        new_ids: The IDs of the problems never judged. Problems answered before (reviews and
            finished ones) are never held back.
        status: The current stage (see current_stage).
    """
    if status.threshold is None:
        return set()
    return {
        problem.problem_id
        for problem in problems
        if problem.points_lost < status.threshold and problem.problem_id in new_ids
    }
