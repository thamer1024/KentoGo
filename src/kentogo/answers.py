"""Connect the quiz and the review features: turn quiz sessions into history records, and back.

The quiz feature (kentogo.quiz) and the review feature (kentogo.review) do not
import each other, as planned in the design memo. This module, like app.py and
today.py, knows both: it makes the record of an answer from a quiz session,
keeps a copy of the problem as JSON text, and turns the kept copies back into
problems.
"""

from __future__ import annotations

import json
from datetime import datetime

from kentogo.mistakes.problem import Problem
from kentogo.quiz.problem_json import problem_from_dict, problem_to_dict
from kentogo.quiz.session import QuizSession
from kentogo.review.history import AnswerHistory
from kentogo.review.record import LOSS_FROM_COMPARE, LOSS_FROM_KATAGO, LOSS_FROM_SGF, LOSS_UNKNOWN, AnswerRecord


def save_answer(
    history: AnswerHistory, session: QuizSession, max_visits: int | None = None, comparison_model: bool = False
) -> None:
    """Save the answer of a session and a copy of its problem, when the result is known.

    Args:
        history: The history.
        session: An answered session. If it is not judged, it is saved without losses.
        max_visits: KataGo's number of visits, if KataGo calculated the losses.
        comparison_model: True if the comparison model (not the main one) calculated the losses.
    """
    data = json.dumps(problem_to_dict(session.problem), ensure_ascii=False)
    history.save(record_of(session, history.now(), max_visits, comparison_model), data)


def saved_problems(history: AnswerHistory, problem_ids: list[str]) -> list[Problem]:
    """Return the problems kept in the history, in the order of the IDs.

    Copies that cannot be read are left out, so that one broken row does not stop the quiz.
    """
    found = history.saved_problem_data(problem_ids)
    problems = []
    for problem_id in problem_ids:
        if problem_id not in found:
            continue
        try:
            problems.append(problem_from_dict(json.loads(found[problem_id])))
        except (KeyError, TypeError, ValueError):
            continue
    return problems


def record_of(
    session: QuizSession, answered_at: datetime, max_visits: int | None = None, comparison_model: bool = False
) -> AnswerRecord:
    """Make the record of the answer of a session.

    Args:
        session: A session that has been answered.
        answered_at: When the answer is saved.
        max_visits: KataGo's number of visits, if the losses were calculated by KataGo.
        comparison_model: True if the comparison model (not the main one) calculated the losses.

    Returns:
        The record, not saved yet. If the answer is not judged yet, the losses and
        the judgment are None.

    Raises:
        ValueError: If the session has not been answered.
    """
    result = session.result
    if result is None:
        raise ValueError("the problem has not been answered yet")
    problem = session.problem
    judged = result.comparison is not None
    return AnswerRecord(
        problem_id=problem.problem_id,
        answered_at=answered_at.isoformat(timespec="seconds"),
        sgf_path=problem.sgf_path,
        move_number=problem.move_number,
        color=result.answer.color,
        answer=result.answer.gtp(),
        actual_move=problem.actual_move.gtp(),
        best_move=problem.best_move.gtp() if problem.best_move else "",
        answer_loss=result.answer_loss,
        actual_loss=result.comparison.actual_loss if judged else None,
        loss_source=_loss_source(judged, max_visits, comparison_model),
        max_visits=max_visits if judged else None,
        correct=result.correct,
        symmetry=session.transform.symmetry,
        swap_colors=session.transform.swap_colors,
    )


def _loss_source(judged: bool, max_visits: int | None, comparison_model: bool) -> str:
    """Return where the losses came from: none if not judged, KataGo if visits are given, else the SGF file."""
    if not judged:
        return LOSS_UNKNOWN
    elif max_visits is None:
        return LOSS_FROM_SGF
    return LOSS_FROM_COMPARE if comparison_model else LOSS_FROM_KATAGO
