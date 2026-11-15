"""Tests for kentogo.fight_setup (what the screen of the local fights uses)."""

from datetime import datetime, timezone

from kentogo.common.types import Move, Position
from kentogo.fight_setup import fight_play, fight_tools
from kentogo.katago.evaluate import EvaluationSettings
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_judge import OPPONENT_RANK, OUTCOME_USER_LEFT, FightOutcome
from kentogo.quiz.fight_settings import FightSettings
from kentogo.quiz.human_line import PlayerRanks
from kentogo.review.history import AnswerHistory
from kentogo.review.store import ReviewStore

EVALUATION = EvaluationSettings(max_visits=800, wide_root_noise=0.04)
POSITION = Position(9, 6.5, "japanese", (), (Move("W", (4, 4)),), "B")
FIGHT = LocalFight("f1", "a.sgf", 2, POSITION, "life_death", ("A1",), (), (), 1, 0.5, (Move("B", (0, 1)),))


def test_how_katago_plays():
    """The engine's visits and noise; the profile of the opponent's rank only with the human-like opponent."""
    strong = fight_play(FightSettings(), EVALUATION, PlayerRanks("15k", "12k"))
    assert (strong.visits, strong.wide_root_noise, strong.profile, strong.tolerance) == (800, 0.04, "", 3.0)
    assert strong.my_profile == ""
    rank = fight_play(FightSettings(OPPONENT_RANK, 5.0), EVALUATION, PlayerRanks("15k", "12k"))
    assert (rank.opponent, rank.profile, rank.my_profile, rank.tolerance) == (
        OPPONENT_RANK,
        "rank_12k",
        "rank_15k",
        5.0,
    )
    assert fight_play(FightSettings(OPPONENT_RANK), EVALUATION, PlayerRanks()).profile == ""


def test_the_tools_make_the_runs_and_save_them():
    history = AnswerHistory(ReviewStore(":memory:"), lambda: datetime(2026, 11, 15, tzinfo=timezone.utc))
    tools = fight_tools(None, EVALUATION, FightSettings(), history, lambda _fight: PlayerRanks())
    run = tools.make_run(FIGHT)
    assert run.fight == FIGHT and run.played == ()
    run.outcome = FightOutcome(OUTCOME_USER_LEFT)
    tools.save(run)
    assert [record.max_visits for record in history.previous("f1")] == [800]
    fight_tools(None, EVALUATION, FightSettings(), None, lambda _fight: PlayerRanks()).save(run)  # No history.
