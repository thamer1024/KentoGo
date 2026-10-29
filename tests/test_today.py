"""Tests for kentogo.today (finding today's problems)."""

import random
from datetime import date, timedelta

from kentogo import today as today_module
from kentogo.answers import save_answer
from kentogo.app_settings import AppSettings
from kentogo.commentary.history import CommentaryHistory
from kentogo.common.types import Move
from kentogo.gui.texts import notice_text
from kentogo.mistakes.extract import ExtractSettings
from kentogo.quiz.collect import collect_problems
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.quiz.session import QuizSession
from kentogo.record.katrain_comment import INTERNAL_MARKER
from kentogo.review.review_settings import ReviewSettings
from kentogo.today import (
    PROJECT_FOLDER,
    default_games_folder,
    exclude_all_problems,
    find_games_folder,
    include_all_problems,
    load_today,
    open_cache,
    open_history,
    prepare_problems,
    read_recorded_colors,
)

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def sgf_with_mistake(loss: float) -> str:
    """Make a game where black's second move loses the given points."""
    comment = (
        f"\nMove 3: B A19\nEstimated point loss: {loss:.1f}\nPredicted top move was Q4 (B+1.0).\nPV: BQ4\n"
        + INTERNAL_MARKER
    )
    return f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd];W[dp];B[aa]C[{comment}])"


def test_collect_problems(tmp_path):
    """Problems are collected from all SGF files, in the order of the file names."""
    (tmp_path / "b.sgf").write_text(sgf_with_mistake(4.0), encoding="utf-8")
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a game", encoding="utf-8")
    problems, skipped = collect_problems(tmp_path, ExtractSettings())
    assert [(p.sgf_path.endswith("a.sgf"), p.points_lost) for p in problems] == [(True, 9.0), (False, 4.0)]
    assert skipped == []


def test_collect_problems_reports_skipped_and_broken_files(tmp_path):
    """Files without a user color, and broken files, are reported and the others are still used."""
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    (tmp_path / "b.sgf").write_text("(;SZ[19]PB[x]PW[y];B[pd])", encoding="utf-8")
    (tmp_path / "c.sgf").write_text(f"(;SZ[9:13]PB[{HUMAN}]PW[{AI}];B[aa])", encoding="utf-8")
    problems, skipped = collect_problems(tmp_path, ExtractSettings())
    assert len(problems) == 1
    assert skipped[0].message() == "b.sgf: skipped (unknown_color)"
    assert skipped[1].message().startswith("c.sgf: cannot read")


def test_find_games_folder(tmp_path):
    """The folder on the command line is used first, then the one in the settings."""
    other = tmp_path / "other"
    other.mkdir()
    assert find_games_folder(other, str(tmp_path)) == (other, None)
    assert find_games_folder(None, str(tmp_path)) == (tmp_path, None)


def test_find_games_folder_default(tmp_path):
    """Without a folder in the settings, the default folder is used, and made if it is missing."""
    default = tmp_path / "games"
    assert find_games_folder(None, "  ", default) == (default, None)
    assert default.is_dir()


def test_default_games_folder_from_the_source():
    """From the source (with pyproject.toml), the default is the "games" folder of the project."""
    assert default_games_folder() == PROJECT_FOLDER / "games"
    assert (PROJECT_FOLDER / "pyproject.toml").is_file()


def test_find_games_folder_problems(tmp_path):
    """Without a usable folder, the app still starts, and the problem is told."""
    folder, problem = find_games_folder(None, str(tmp_path / "missing"))
    assert folder is None and "missing" in notice_text(problem)
    blocked = tmp_path / "file"
    blocked.write_text("x")
    folder, problem = find_games_folder(None, "", blocked / "games")  # The default cannot be made.
    assert folder is None and "games" in notice_text(problem)


def test_open_history(tmp_path):
    """The history is kept next to the settings file. A broken file is not used, but does not stop the app."""
    history = open_history(tmp_path / "settings.json")
    assert history.store.path == tmp_path / "history.sqlite3"
    history.store.close()

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "history.sqlite3").write_text("not a database")
    assert open_history(broken / "settings.json") is None
    notices = []
    assert open_history(broken / "settings.json", notices) is None
    assert len(notices) == 1 and "履歴" in notice_text(notices[0])


def answer_first_problem(history, folder, gtp_point: str) -> None:
    """Answer the first problem of a folder with a point (the game move is A19, the best move Q4)."""
    today = prepare_problems(folder, AppSettings(), history, random.Random(0))
    session = QuizSession(today.problems[0], ScoringPolicy())
    session.answer(Move.from_gtp(gtp_point, "B"))
    save_answer(history, session)


class Tomorrow(date):
    """A date whose today() is tomorrow, to see the problems of the next day."""

    @classmethod
    def today(cls) -> date:
        """Return tomorrow."""
        return date.today() + timedelta(days=1)


def test_prepare_problems_with_history(tmp_path, monkeypatch):
    """A problem answered wrong is not asked again the same day, but the next day; answered correctly, it waits."""
    games = tmp_path / "games"
    games.mkdir()
    (games / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    history = open_history(tmp_path / "settings.json")
    today = prepare_problems(games, AppSettings(), history, random.Random(0))
    assert (len(today.problems), today.new_count, today.review_count, today.message) == (1, 1, 0, None)

    answer_first_problem(history, games, "A19")  # The game move: wrong, so it is asked again tomorrow.
    today = prepare_problems(games, AppSettings(), history, random.Random(0))
    assert today.problems == []
    assert "今日の問題はありません" in notice_text(today.message)

    monkeypatch.setattr(today_module, "date", Tomorrow)
    today = prepare_problems(games, AppSettings(), history, random.Random(0))
    assert (len(today.problems), today.new_count, today.review_count) == (1, 0, 1)

    answer_first_problem(history, games, "Q4")  # The best move: correct, so it waits 3 days.
    assert prepare_problems(games, AppSettings(), history, random.Random(0)).problems == []
    history.store.close()


def test_prepare_problems_without_folder_or_history(tmp_path):
    """Without a folder, the reason is given. Without a history, all problems are asked as new ones."""
    assert prepare_problems(None, AppSettings(), None, random.Random(0)).problems == []
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    today = prepare_problems(tmp_path, AppSettings(), None, random.Random(0))
    assert (len(today.problems), today.new_count, today.message) == (1, 1, None)


def test_load_today_reports_progress(tmp_path):
    """load_today opens its own cache and history, reads the games, and reports the progress."""
    games = tmp_path / "games"
    games.mkdir()
    for name in ("a", "b", "c"):
        (games / f"{name}.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    steps = []
    today = load_today(
        tmp_path / "settings.json", games, AppSettings(), random.Random(0), progress=lambda *step: steps.append(step)
    )
    assert steps == [(1, 3), (2, 3), (3, 3)]
    assert today.new_count == 1  # The three games have the same position, so it is one problem.
    assert (tmp_path / "problem_cache.sqlite3").exists()
    assert (tmp_path / "history.sqlite3").exists()


def test_open_cache(tmp_path):
    """The problem cache is kept next to the settings file. A broken file is not used, but does not stop the app."""
    cache = open_cache(tmp_path / "settings.json")
    assert cache.path == tmp_path / "problem_cache.sqlite3"
    cache.close()
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "problem_cache.sqlite3").write_text("not a database")
    assert open_cache(tmp_path / "broken" / "settings.json") is None
    notices = []
    assert open_cache(tmp_path / "broken" / "settings.json", notices) is None
    assert len(notices) == 1 and "キャッシュ" in notice_text(notices[0])


def test_load_today_tells_the_cache_problem(tmp_path):
    """When the cache cannot be used, the problems are still made, and the user is told why it is slow."""
    games = tmp_path / "games"
    games.mkdir()
    (games / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    (tmp_path / "problem_cache.sqlite3").write_text("not a database")
    today = load_today(tmp_path / "settings.json", games, AppSettings(), random.Random(0))
    assert len(today.problems) == 1
    assert len(today.notices) == 1 and "キャッシュ" in notice_text(today.notices[0])


def three_games(tmp_path):
    """Make a games folder with three games whose mistakes are in different positions."""
    games = tmp_path / "games"
    games.mkdir()
    for name, moves in (("a", "B[pd];W[dp]"), ("b", "B[dd];W[pp]"), ("c", "B[pq];W[dc]")):
        comment = f"\nMove 3: B A19\nEstimated point loss: 9.0\nPredicted top move was Q4 (B+1.0).\nPV: BQ4\n{INTERNAL_MARKER}"
        sgf = f"(;SZ[19]PB[{HUMAN}]PW[{AI}];{moves};B[aa]C[{comment}])"
        (games / f"{name}.sgf").write_text(sgf, encoding="utf-8")
    return games


def test_exclude_and_include_all(tmp_path):
    """All current problems can be set aside, and later all problems can be started again."""
    games = three_games(tmp_path)
    settings_path = tmp_path / "settings.json"
    assert exclude_all_problems(settings_path, games, QuizSettings()) == 3
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).problems == []

    include_all_problems(settings_path)
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 3


def test_include_all_brings_back_done_problems(tmp_path):
    """After a reset, a problem answered correctly before is asked again as a new problem."""
    games = three_games(tmp_path)
    settings_path = tmp_path / "settings.json"
    history = open_history(settings_path)
    answer_first_problem(history, games, "Q4")  # Correct: done.
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 2

    include_all_problems(settings_path)
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 3
    history.store.close()


def test_the_limit_is_for_the_day(tmp_path):
    """The limit is for a day: answers given earlier today count, and when it is reached nothing is asked."""
    games = three_games(tmp_path)
    settings_path = tmp_path / "settings.json"
    limited = AppSettings(review=ReviewSettings(session_limit=2))
    today = load_today(settings_path, games, limited, random.Random(0))
    assert (len(today.problems), today.session_limit) == (2, 2)

    history = open_history(settings_path)
    answer_first_problem(history, games, "A19")  # Wrong: asked again today.
    today = load_today(settings_path, games, limited, random.Random(0))
    assert (len(today.problems), today.session_limit) == (1, 1)
    answer_first_problem(history, games, "A19")
    today = load_today(settings_path, games, limited, random.Random(0))
    assert (today.problems, today.session_limit, today.message.key) == ([], 0, "daily_done")
    unlimited = AppSettings(review=ReviewSettings(session_limit=2, daily_limit_off=True))
    assert load_today(settings_path, games, unlimited, random.Random(0)).session_limit is None
    history.store.close()
    assert (
        load_today(
            settings_path, games, AppSettings(review=ReviewSettings(session_limit=0)), random.Random(0)
        ).session_limit
        is None
    )


def test_review_is_kept_when_the_game_is_gone(tmp_path, monkeypatch):
    """A problem in review is still asked when its game no longer makes it (here the file is deleted)."""
    games = three_games(tmp_path)
    settings_path = tmp_path / "settings.json"
    history = open_history(settings_path)
    answer_first_problem(history, games, "A19")  # Wrong: asked again tomorrow.
    first = sorted(games.glob("*.sgf"))[0]
    first.unlink()
    monkeypatch.setattr(today_module, "date", Tomorrow)
    today = load_today(settings_path, games, AppSettings(), random.Random(0))
    assert (today.new_count, today.review_count) == (2, 1)
    assert today.problems[-1].sgf_path == str(first)
    history.store.close()


def test_skipped_games_are_counted(tmp_path):
    """The games that give no problems are counted by reason for the start screen."""
    (tmp_path / "a.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    (tmp_path / "b.sgf").write_text("(;SZ[19]PB[x]PW[y];B[pd])", encoding="utf-8")
    (tmp_path / "c.sgf").write_text(f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd])", encoding="utf-8")
    today = prepare_problems(tmp_path, AppSettings(), None, random.Random(0))
    assert today.skipped == {"unknown_color": 1, "no_analysis": 1}
    assert [game.name for game in today.skipped_games] == ["b.sgf", "c.sgf"]


def test_load_today_uses_recorded_colors(tmp_path):
    """A game between two humans gives problems when the user gave the color in the list of games."""
    games = tmp_path / "games"
    games.mkdir()
    (games / "a.sgf").write_text(sgf_with_mistake(9.0).replace(f"PW[{AI}]", f"PW[{HUMAN}]"), encoding="utf-8")
    settings_path = tmp_path / "settings.json"
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 0
    history = CommentaryHistory(tmp_path / "commentary_history.sqlite3")
    history.save_inputs("a.sgf", "B", "18k", "")
    history.close()
    assert read_recorded_colors(settings_path) == {"a.sgf": "B"}
    assert load_today(settings_path, games, AppSettings(), random.Random(0)).new_count == 1


def test_read_recorded_colors_without_or_with_a_broken_database(tmp_path):
    """No database, or a broken one, gives no colors (the quiz still works)."""
    assert read_recorded_colors(tmp_path / "settings.json") == {}
    assert not (tmp_path / "commentary_history.sqlite3").exists()  # Not made just to read it.
    (tmp_path / "commentary_history.sqlite3").write_text("not a database")
    assert read_recorded_colors(tmp_path / "settings.json") == {}
