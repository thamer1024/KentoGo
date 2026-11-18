"""How far the problems are: how many are finished, in progress and not started yet."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from kentogo.repetition.schedule import NEW, STATE_DONE, STATE_NEW, STATE_REVIEW, ReviewState


@dataclass(frozen=True)
class ProblemCounts:
    """The number of problems in each state.

    Attributes:
        done: The problems that are finished.
        in_progress: The problems answered at least once and not finished yet.
        untouched: The problems without a judged answer.
    """

    done: int = 0
    in_progress: int = 0
    untouched: int = 0

    @property
    def total(self) -> int:
        """Return the number of all the problems."""
        return self.done + self.in_progress + self.untouched


def count_problems(problem_ids: Iterable[str], states: Mapping[str, ReviewState]) -> ProblemCounts:
    """Count the problems in each state.

    Args:
        problem_ids: The problems to count. An ID given twice is counted once.
        states: The review state of each problem ID. A missing ID is a new problem.
    """
    found = [states.get(problem_id, NEW).state for problem_id in set(problem_ids)]
    return ProblemCounts(found.count(STATE_DONE), found.count(STATE_REVIEW), found.count(STATE_NEW))
