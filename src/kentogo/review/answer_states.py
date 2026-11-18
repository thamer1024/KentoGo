"""The answers of a history, and the state of each problem worked out from them."""

from __future__ import annotations

from kentogo.repetition.modes import REVIEW_ONCE
from kentogo.repetition.schedule import ReviewState, review_state
from kentogo.review.history import AnswerHistory
from kentogo.review.record import AnswerRecord
from kentogo.review.review_settings import ReviewSettings


def answers_and_states(
    history: AnswerHistory | None, review: ReviewSettings
) -> tuple[list[AnswerRecord], dict[str, ReviewState]]:
    """Return all answers, the oldest first, and the state of each answered problem (since the last reset)."""
    if history is None:
        return [], {}
    by_problem = history.all_previous()
    last_reset = history.last_reset()
    once = review.review_mode == REVIEW_ONCE
    states = {
        problem_id: review_state(
            [record for record in records if record.record_id > last_reset], review.review_streak, once
        )
        for problem_id, records in by_problem.items()
    }
    answers = sorted((record for records in by_problem.values() for record in records), key=lambda r: r.record_id)
    return answers, states
