"""Connect the local fight problems and the review feature: turn a played fight into a history record, and back.

Like answers (for the mistake problems), this module knows both the quiz feature (quiz.fight_run) and the review
feature (review). The answers of the fights are kept in their own history (see fights_today), in the same table
as the mistake problems' answers, with these meanings:

- answer: the moves played from the fight's position, both colors, in GTP coordinates separated by spaces
  (such as "A2 B2 C2"; the last one is the user's, even when it left the fight);
- actual_move: the move of the game at the fight's position;
- best_move: how the fight ended (quiz.fight_judge.OUTCOME_WON, ...);
- answer_loss: how many points the user's score fell since the start, or None if not known;
- max_visits: KataGo's visits of each reading;
- correct: the outcome (True only when the fight was won and the score held).

The fights may be shown turned, but their moves are always saved in the original coordinates.
"""

from __future__ import annotations

import json
from datetime import datetime

from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_run import FightRun
from kentogo.quiz.problem_json import local_fight_from_dict, local_fight_to_dict
from kentogo.review.history import AnswerHistory
from kentogo.review.record import LOSS_FROM_KATAGO, LOSS_UNKNOWN, AnswerRecord


def save_fight_answer(history: AnswerHistory, run: FightRun, visits: int) -> None:
    """Save the answer of a fight that has ended, and a copy of the fight.

    Args:
        history: The history of the fights.
        run: A fight that has ended.
        visits: KataGo's visits of each reading.

    Raises:
        ValueError: If the fight has not ended.
    """
    data = json.dumps(local_fight_to_dict(run.fight), ensure_ascii=False)
    history.save(fight_record(run, history.now(), visits), data)


def fight_record(run: FightRun, answered_at: datetime, visits: int) -> AnswerRecord:
    """Make the record of a fight that has ended (not saved yet).

    Raises:
        ValueError: If the fight has not ended.
    """
    outcome = run.outcome
    if outcome is None:
        raise ValueError("the fight has not ended yet")
    fight = run.fight
    return AnswerRecord(
        problem_id=fight.problem_id,
        answered_at=answered_at.isoformat(timespec="seconds"),
        sgf_path=fight.sgf_path,
        move_number=fight.move_number,
        color=run.color,
        answer=" ".join(move.gtp() for move in run.played),
        actual_move=fight.game_line[0].gtp() if fight.game_line else "",
        best_move=outcome.kind,
        answer_loss=outcome.score_loss,
        actual_loss=None,
        loss_source=LOSS_UNKNOWN if outcome.score_loss is None else LOSS_FROM_KATAGO,
        max_visits=visits,
        correct=outcome.correct,
        symmetry=0,
        swap_colors=False,
    )


def saved_fights(history: AnswerHistory, problem_ids: list[str]) -> list[LocalFight]:
    """Return the fights kept in the history, in the order of the IDs (copies that cannot be read are left out)."""
    found = history.saved_problem_data(problem_ids)
    fights = []
    for problem_id in problem_ids:
        if problem_id not in found:
            continue
        try:
            fights.append(local_fight_from_dict(json.loads(found[problem_id])))
        except (KeyError, TypeError, ValueError):
            continue
    return fights
