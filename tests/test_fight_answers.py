"""Tests for kentogo.fight_answers (the answers of the local fight problems in their history)."""

from datetime import datetime, timezone

import pytest

from kentogo.common.types import Move, Position
from kentogo.fight_answers import fight_record, save_fight_answer, saved_fights
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_judge import OUTCOME_LOST, OUTCOME_SCORE, FightOutcome
from kentogo.quiz.fight_run import FightPlay, FightRun
from kentogo.review.history import AnswerHistory
from kentogo.review.store import ReviewStore

WHEN = datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc)
POSITION = Position(9, 6.5, "japanese", (), (Move("W", (4, 4)),), "B")
LINE = (Move("B", (0, 1)), Move("W", (1, 1)))
FIGHT = LocalFight("f1", "a.sgf", 2, POSITION, "life_death", ("A1", "B1", "C1"), (), (), 2, 0.5, LINE)


def ended(played: tuple[str, ...], outcome: FightOutcome | None) -> FightRun:
    """A fight played (no engine is used: the moves and the outcome are set)."""
    run = FightRun(None, FIGHT, FightPlay(500, None))
    colors = ("B", "W")
    run.played = tuple(Move.from_gtp(point, colors[index % 2]) for index, point in enumerate(played))
    run.outcome = outcome
    return run


def test_the_record_of_a_fight():
    record = fight_record(ended(("A2", "B2", "C2"), FightOutcome(OUTCOME_SCORE, 4.5)), WHEN, 500)
    assert (record.problem_id, record.move_number, record.color) == ("f1", 2, "B")
    assert (record.answer, record.actual_move, record.best_move) == ("A2 B2 C2", "A2", OUTCOME_SCORE)
    assert (record.answer_loss, record.loss_source, record.max_visits, record.correct) == (4.5, "katago", 500, False)
    left = fight_record(ended(("J9",), FightOutcome(OUTCOME_LOST, None, left=True)), WHEN, 500)
    assert (left.answer, left.best_move, left.answer_loss, left.loss_source) == ("J9", "lost_left", None, "")


def test_a_fight_that_has_not_ended_is_not_saved():
    with pytest.raises(ValueError):
        fight_record(ended(("A2",), None), WHEN, 500)


def test_the_answer_and_the_fight_are_kept():
    history = AnswerHistory(ReviewStore(":memory:"), lambda: WHEN)
    save_fight_answer(history, ended(("J9",), FightOutcome(OUTCOME_LOST)), 500)
    (record,) = history.previous("f1")
    assert (record.answered_at, record.correct) == (WHEN.isoformat(timespec="seconds"), False)
    assert saved_fights(history, ["f1", "missing"]) == [FIGHT]
