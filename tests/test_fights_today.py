"""Tests for kentogo.fights_today (today's local fight problems)."""

import random
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from kentogo.app_settings import FIGHT_REVIEW, AppSettings
from kentogo.common.types import Move, Position
from kentogo.fights_today import (
    askable_fights,
    fight_history_path,
    load_fight_summary,
    load_fights,
    plan_fights,
    prepare_fights,
)
from kentogo.mistakes.local_fight import KIND_BOUNDARY, KIND_LIFE_DEATH, LocalFight
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.record.kentogo_analysis import KGA_PROPERTY, encode_kga
from kentogo.repetition.counts import ProblemCounts
from kentogo.report import load_fight_results
from kentogo.review.history import AnswerHistory
from kentogo.review.record import AnswerRecord
from kentogo.review.store import ReviewStore

FIGHT = {"kind": "life_death", "mine": ["A19", "B19", "C19"], "theirs": [], "points": [], "moves": 1}


def game_text(first: str, fight: bool = True) -> str:
    """A game of Me (black) with a local fight after white's move 2 (black plays move 3 in it)."""
    data = {"root": {"scoreLead": 0.0}, "moves": {}, **({"local_fight": FIGHT} if fight else {})}
    kga = KGA_PROPERTY + "".join(f"[{value}]" for value in encode_kga(data))
    return f"(;SZ[19]PB[Me]PW[Bot];B[{first}];W[dp]{kga};B[aa];W[dd])"


def games_with_fights(tmp_path):
    """A games folder with two games (other first moves: other positions), each with a local fight."""
    folder = tmp_path / "games"
    folder.mkdir()
    for name, first in (("a", "pd"), ("b", "qd")):
        (folder / f"{name}.sgf").write_text(game_text(first), encoding="utf-8")
    return folder


def settings_for(folder) -> AppSettings:
    return AppSettings(quiz=QuizSettings.from_dict({"games_folder": str(folder), "my_names": ["Me"]}))


def wrong_answer(fight, when: datetime) -> AnswerRecord:
    return AnswerRecord(
        fight.problem_id,
        when.isoformat(),
        fight.sgf_path,
        fight.move_number,
        "B",
        "A1",
        "",
        "",
        None,
        None,
        "",
        None,
        False,
        0,
        False,
    )


def test_without_a_history_every_fight_is_asked(tmp_path):
    folder = games_with_fights(tmp_path)
    today = prepare_fights(None, settings_for(folder), None, random.Random(0))
    assert today.new_count == 2 and [fight.move_number for fight in today.fights] == [3, 3]


def test_fights_have_their_own_limit_and_reviews(tmp_path):
    """The fights' limit of the day (5 at first, here 1) is used, and a fight answered wrong comes back the next day."""
    folder = games_with_fights(tmp_path)
    history = AnswerHistory(ReviewStore(":memory:"))
    settings = replace(settings_for(folder), fights=replace(FIGHT_REVIEW, session_limit=1))
    today = prepare_fights(None, settings, history, random.Random(0))
    assert (len(today.fights), today.new_count, today.session_limit) == (1, 1, 1)

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    for fight in prepare_fights(None, settings_for(folder), None, random.Random(0)).fights:
        history.save(wrong_answer(fight, yesterday))
    plan, limit = plan_fights(today.fights, history, AppSettings().fights, date.today())
    assert (plan.review_count, plan.new_count, limit) == (1, 0, 5)


def test_no_fights_and_the_history_file(tmp_path):
    """A folder without fights says so; the fights' history is its own file next to the settings."""
    folder = tmp_path / "games"
    folder.mkdir()
    (folder / "a.sgf").write_text(game_text("pd", fight=False), encoding="utf-8")
    today = load_fights(tmp_path / "settings.json", None, settings_for(folder), random.Random(0))
    assert today.fights == [] and today.message.key == "fights_none"
    assert fight_history_path(tmp_path / "settings.json") == tmp_path / "fight_history.sqlite3"
    assert (tmp_path / "fight_history.sqlite3").is_file()


def test_the_results_of_the_fights_come_from_their_own_history(tmp_path):
    settings_path = tmp_path / "settings.json"
    fight = prepare_fights(None, settings_for(games_with_fights(tmp_path)), None, random.Random(0)).fights[0]
    history = AnswerHistory(ReviewStore(fight_history_path(settings_path)))
    history.save(wrong_answer(fight, datetime.now(timezone.utc)))
    history.store.close()
    results = load_fight_results(settings_path, AppSettings())
    assert (results.totals.answered, results.totals.correct, len(results.days)) == (1, 0, 1)


def test_the_summary_counts_the_current_fights(tmp_path):
    """The summary counts all the fights given, except those set aside, and needs an answer of today."""
    settings_path = tmp_path / "settings.json"
    today = prepare_fights(None, settings_for(games_with_fights(tmp_path)), None, random.Random(0))
    review = AppSettings().fights
    assert len(today.all_ids) == 2
    assert load_fight_summary(settings_path, date.today(), today.all_ids, review) is None

    answered, other = today.fights
    history = AnswerHistory(ReviewStore(fight_history_path(settings_path)))
    history.save(wrong_answer(answered, datetime.now(timezone.utc)))
    history.store.close()
    summary = load_fight_summary(settings_path, date.today(), today.all_ids, review)
    assert (summary.answered, summary.correct, summary.counts) == (1, 0, ProblemCounts(0, 1, 1))

    history = AnswerHistory(ReviewStore(fight_history_path(settings_path)))
    history.store.exclude([other.problem_id], datetime.now(timezone.utc).isoformat())
    history.store.close()
    assert load_fight_summary(settings_path, date.today(), today.all_ids, review).counts == ProblemCounts(0, 1, 0)


def test_a_fight_with_no_point_to_judge_is_not_asked():
    """A life and death fight needs stones, and a boundary needs empty points."""
    position = Position(9, 6.5, "japanese", (), (Move("W", (4, 4)),), "B")

    def local_fight(kind: str, mine: tuple = (), points: tuple = ()) -> LocalFight:
        return LocalFight("f", "a.sgf", 2, position, kind, mine, (), points, 1, 0.5, ())

    stones, no_stones = local_fight(KIND_LIFE_DEATH, mine=("A1",)), local_fight(KIND_LIFE_DEATH, points=("A2",))
    points, no_points = local_fight(KIND_BOUNDARY, points=("A2",)), local_fight(KIND_BOUNDARY, mine=("A1",))
    assert askable_fights([stones, no_stones, points, no_points]) == [stones, points]


def test_the_fights_review_settings_are_their_own():
    """The "fights" part of settings.json has its own review settings, 5 fights a day at first."""
    assert AppSettings().fights.session_limit == 5 and AppSettings().review.session_limit == 20
    settings = AppSettings.from_sections({"fights": {"review_streak": 3}})
    assert (settings.fights.review_streak, settings.fights.session_limit) == (3, 5)
    assert AppSettings.from_sections(settings.sections()) == settings
