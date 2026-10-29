"""Choose the problems to ask today: problems never answered, and the reviews that are due.

Problems answered correctly, reviews whose day has not come yet, and problems
set aside by the user are not asked. The settings decide which group comes
first: new problems, reviews, or a mix (two reviews, then one new problem).
Inside each group, the problems keep the order chosen in the settings (file
name, newest, random), except the reviews: those answered wrong last time come first, and
then the others; in each, the one that has waited longest comes first. When there is a limit,
only that many are asked.

The same position can be in two SGF files (for example a game saved twice).
It has one problem ID and one history, so it is asked only once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Generic, Protocol, TypeVar

from kentogo.repetition.modes import PRIORITY_MIX, PRIORITY_NEW
from kentogo.repetition.schedule import NEW, STATE_NEW, ReviewState


class HasProblemId(Protocol):
    """Anything with a problem ID, such as a quiz problem. The plan needs nothing else."""

    problem_id: str


Item = TypeVar("Item", bound=HasProblemId)

# In the mix order: this many reviews, then one new problem.
MIX_REVIEWS = 2


@dataclass(frozen=True)
class QuizPlan(Generic[Item]):
    """The problems to ask today.

    Attributes:
        problems: The problems in the order they are asked.
        new_count: How many of them were never answered.
        review_count: How many of them are reviews.
    """

    problems: list[Item]
    new_count: int
    review_count: int


def plan_problems(
    problems: list[Item],
    states: dict[str, ReviewState],
    today: date,
    priority: str,
    excluded: set[str] = frozenset(),
    limit: int | None = None,
) -> QuizPlan[Item]:
    """Choose and order the problems to ask today.

    Args:
        problems: All problems (anything with a problem_id), in the order chosen in the settings.
        states: The review state of each problem ID. A missing ID is a new problem.
        today: Today's date.
        priority: PRIORITY_NEW, PRIORITY_REVIEW or PRIORITY_MIX.
        excluded: The IDs of the problems set aside by the user.
        limit: The most problems to ask, or None for no limit.

    Returns:
        The plan.
    """
    new: list[Item] = []
    reviews: list[Item] = []
    seen: set[str] = set(excluded)
    for problem in problems:
        if problem.problem_id in seen:
            continue
        seen.add(problem.problem_id)
        state = states.get(problem.problem_id, NEW)
        if state.state == STATE_NEW:
            new.append(problem)
        elif state.is_due(today):
            reviews.append(problem)
    reviews.sort(key=lambda problem: _review_order(states[problem.problem_id]))  # Stable: equal keys keep their order.
    if priority == PRIORITY_NEW:
        ordered = new + reviews
    elif priority == PRIORITY_MIX:
        ordered = _mix(reviews, new)
    else:
        ordered = reviews + new
    if limit is not None:
        ordered = ordered[:limit]
    review_ids = {problem.problem_id for problem in reviews}
    review_count = sum(1 for problem in ordered if problem.problem_id in review_ids)
    return QuizPlan(ordered, len(ordered) - review_count, review_count)


def _review_order(state: ReviewState) -> tuple[bool, date]:
    """Return the sort key of a review: answered wrong last time first, then the longest wait first."""
    return (not state.last_wrong, state.due)


def _mix(reviews: list[Item], new: list[Item]) -> list[Item]:
    """Put MIX_REVIEWS reviews, then one new problem, and so on. When one list ends, the other goes on."""
    mixed: list[Item] = []
    review_index = new_index = 0
    while review_index < len(reviews) or new_index < len(new):
        mixed.extend(reviews[review_index : review_index + MIX_REVIEWS])
        review_index += MIX_REVIEWS
        if new_index < len(new):
            mixed.append(new[new_index])
            new_index += 1
    return mixed
