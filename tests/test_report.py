"""Tests for kentogo.report (the report and the summary of the day)."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from kentogo.app_settings import AppSettings
from kentogo.common.types import Move, Position
from kentogo.mistakes.problem import Problem
from kentogo.record.katrain_comment import INTERNAL_MARKER
from kentogo.repetition.schedule import DONE, NEW
from kentogo.report import (
    Achievement,
    DayResult,
    GameAverages,
    GameMistakes,
    Recent,
    Totals,
    day_results,
    game_averages,
    game_mistakes,
    game_time,
    load_report,
    recent_results,
    recovered_points,
    today_summary,
    totals,
)
from kentogo.today import open_history

TODAY = date(2026, 11, 6)


@dataclass(frozen=True)
class Answer:
    """An answer: only what the report needs."""

    problem_id: str
    answered_at: str
    actual_loss: float | None
    answer_loss: float | None
    correct: bool | None


def answer(day: date, actual: float, given: float, correct: bool, problem_id: str = "p") -> Answer:
    """An answer given at noon of a day (in the time zone of the computer)."""
    at = datetime(day.year, day.month, day.day, 12, 0).astimezone()
    return Answer(problem_id, at.isoformat(), actual, given, correct)


def days_ago(count: int) -> date:
    """The day some days before TODAY."""
    return TODAY - timedelta(days=count)


def test_recovered_points_only_for_correct_answers():
    assert recovered_points(answer(TODAY, 10.0, 2.0, True)) == 8.0
    assert recovered_points(answer(TODAY, 10.0, -0.5, True)) == 10.0  # Better than the best move counts as 0 lost.
    assert recovered_points(answer(TODAY, 10.0, 2.0, False)) == 0.0
    assert recovered_points(Answer("p", "2026-11-06T12:00:00+09:00", None, 1.0, True)) == 0.0


def test_day_results_count_only_practice_days():
    """Days without practice are not in the list, so they never pull the numbers down."""
    answers = [
        answer(days_ago(9), 10.0, 5.0, False),
        answer(days_ago(9), 10.0, 1.0, True),
        answer(TODAY, 10.0, 2.0, True),
        answer(TODAY, 2.0, 2.0, True),  # A small problem: not in the average.
        Answer("p", answer(TODAY, 1, 1, True).answered_at, None, None, None),  # Not judged: left out.
    ]
    assert day_results(answers, 3.0) == [
        DayResult(days_ago(9), 2, 1, 0.7, 9.0),
        DayResult(TODAY, 2, 2, 0.8, 8.0),
    ]


def test_recent_compares_the_latest_5_practice_days_with_the_5_before():
    old = [answer(days_ago(30 + day), 10.0, 5.0, day % 2 == 0) for day in range(5)]  # 3 of 5 correct, 50% back.
    new = [answer(days_ago(day * 3), 10.0, 1.0, True) for day in range(5)]  # Gaps between the days do not matter.
    recent = recent_results(old + new, 3.0)
    expected = Recent(1.0, 0.9, 0.6, 0.5)
    for name in ("correct_rate", "average", "earlier_correct_rate", "earlier_average"):
        assert getattr(recent, name) == pytest.approx(getattr(expected, name))
    assert recent_results([], 3.0) == Recent()


def test_totals():
    answers = [answer(days_ago(2), 10.0, 1.0, True, "a"), answer(TODAY, 8.0, 7.0, False, "b")]
    assert totals(answers, {"a": DONE, "b": NEW}) == Totals(2, 1, 1, 9.0, 2)


def test_game_time_from_the_file_name_or_the_file():
    assert game_time(Path("KaTrain_人間 vs AI 2026-10-30 17 43 32.sgf")) == datetime(2026, 10, 30, 17, 43, 32)
    assert game_time(Path("fox.sgf"), lambda _path: 0.0) == datetime.fromtimestamp(0.0)


PROBLEM = Problem(
    problem_id="",
    sgf_path="a.sgf",
    move_number=3,
    position=Position(19, 6.5, "japanese", (), (), "B"),
    actual_move=Move.from_gtp("A19", "B"),
    best_move=None,
    points_lost=8.0,
)


def test_game_mistakes_count_big_and_large_mistakes_of_every_game():
    problems = [replace(PROBLEM, sgf_path="/g/a.sgf", points_lost=loss) for loss in (25.0, 12.0, 10.0, 4.0)]
    games = {Path("/g/b.sgf"): datetime(2026, 11, 2), Path("/g/a.sgf"): datetime(2026, 11, 1)}
    assert game_mistakes(problems, games) == [
        GameMistakes("a.sgf", datetime(2026, 11, 1), 1, 2),
        GameMistakes("b.sgf", datetime(2026, 11, 2), 0, 0),  # A game without big mistakes counts too.
    ]


def test_game_averages_of_the_latest_5_games_and_the_5_before():
    games = [GameMistakes(f"{n}.sgf", datetime(2026, 10, 1 + n), 2, 1) for n in range(5)]
    games += [GameMistakes(f"x{n}.sgf", datetime(2026, 10, 10 + n), n % 2, 0) for n in range(5)]
    assert game_averages(games) == GameAverages(0.4, 0.0, 2.0, 1.0)
    assert game_averages([]) == GameAverages()


def test_today_summary_with_milestones_and_a_cleared_stage():
    problems = [
        replace(PROBLEM, problem_id="big", points_lost=25.0),
        replace(PROBLEM, problem_id="mid", points_lost=12.0),
    ]
    before = [answer(days_ago(1), 100.0, 5.0, True, "x")] + [answer(days_ago(1), 10.0, 1.0, True, "x")] * 98
    todays = [answer(TODAY, 30.0, 5.0, True, "big"), answer(TODAY, 12.0, 11.0, False, "mid")]
    summary = today_summary(before + todays, TODAY, problems, (20.0, 10.0))
    assert (summary.answered, summary.correct, summary.recovered, summary.day_number) == (2, 1, 25.0, 2)
    assert summary.achievements == (
        Achievement("stage_cleared", 20.0),  # The 25-point problem was answered correctly today.
        Achievement("correct_milestone", 100),  # 99 correct answers before today, 100 now.
        Achievement("recovered_milestone", 1000),  # 977 points before today, 1002 now.
    )
    assert today_summary(before, TODAY, problems, (20.0, 10.0)) is None  # Nothing answered today.


def test_last_stage_cleared_only_once():
    problems = [replace(PROBLEM, problem_id="mid", points_lost=12.0)]
    first = [answer(days_ago(1), 12.0, 1.0, True, "mid")]
    summary = today_summary([*first, answer(TODAY, 12.0, 1.0, True, "mid")], TODAY, problems, (20.0, 10.0))
    assert summary.achievements == ()  # Both stages were cleared yesterday already.


HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def sgf_game(loss: float, setup: str = "B[pd];W[dp]") -> str:
    """A game where the user (black) loses some points with move 3 (as in tests/test_today.py)."""
    comment = (
        f"\nMove 3: B A19\nEstimated point loss: {loss:.1f}\nPredicted top move was Q4 (B+1.0).\nPV: BQ4\n"
        + INTERNAL_MARKER
    )
    return f"(;SZ[19]PB[{HUMAN}]PW[{AI}];{setup};B[aa]C[{comment}])"


def test_load_report_from_the_games_and_the_history(tmp_path):
    games = tmp_path / "games"
    games.mkdir()
    (games / "g 2026-10-01 10 00 00.sgf").write_text(sgf_game(25.0), encoding="utf-8")
    (games / "g 2026-10-02 10 00 00.sgf").write_text(sgf_game(12.0, "B[dd];W[pp]"), encoding="utf-8")
    open_history(tmp_path / "settings.json").store.close()  # An empty history.
    report = load_report(tmp_path / "settings.json", games, AppSettings())
    assert [(game.big, game.large) for game in report.games] == [(1, 0), (0, 1)]
    assert report.totals == Totals()
    assert report.pass_ratio == AppSettings().quiz.scoring.pass_ratio
