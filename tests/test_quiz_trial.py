"""Tests for kentogo.quiz_trial (asking every problem of one kind of the games analyzed by KentoGo)."""

from kentogo import quiz_trial
from kentogo.app import parse_arguments
from kentogo.app_settings import AppSettings
from kentogo.gui.texts import notice_text
from kentogo.mistakes.extract import ExtractSettings
from kentogo.quiz.collect import collect_games
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.quiz_trial import (
    TRIAL_LOSS,
    TRIAL_PUNISH,
    analyzed_by_kentogo_file,
    kentogo_games,
    load_trial,
    trial_problems,
)
from kentogo.record.katrain_comment import INTERNAL_MARKER

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def sgf_with_mistake(loss: float) -> str:
    """Make a game where black's second move loses the given points (as in test_today)."""
    comment = (
        f"\nMove 3: B A19\nEstimated point loss: {loss:.1f}\nPredicted top move was Q4 (B+1.0).\nPV: BQ4\n"
        + INTERNAL_MARKER
    )
    return f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd];W[dp];B[aa]C[{comment}])"


def sgf_after_white_mistake(white_loss: float) -> str:
    """Make a game where white's move 2 loses the given points, then black's move 3 loses 8 (as in test_today)."""
    white = f"\nMove 2: W D4\nEstimated point loss: {white_loss:.1f}\nPredicted top move was D16 (B+1.0).\n{INTERNAL_MARKER}"
    black = (
        f"\nMove 3: B A19\nEstimated point loss: 8.0\nPredicted top move was Q4 (B+1.0).\nPV: BQ4\n{INTERNAL_MARKER}"
    )
    return f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[dd];W[dp]C[{white}];B[aa]C[{black}])"


def write_games(folder):
    """Write a game with a punishment problem (a.sgf), and one with a mistake by the points lost (b.sgf)."""
    folder.mkdir()
    (folder / "a.sgf").write_text(sgf_after_white_mistake(20.0), encoding="utf-8")
    (folder / "b.sgf").write_text(sgf_with_mistake(9.0), encoding="utf-8")
    return folder


def test_the_problems_of_each_kind(tmp_path):
    """Loss gives the mistakes that are not punishment problems, punish only the punishment problems."""
    games, _skipped = collect_games(write_games(tmp_path / "games"), ExtractSettings())
    losses = trial_problems(games, TRIAL_LOSS)
    punishments = trial_problems(games, TRIAL_PUNISH)
    assert [problem.sgf_path.endswith("b.sgf") for problem in losses] == [True]
    assert [problem.punishment for problem in punishments] == ["punish"]


def test_only_the_games_analyzed_by_kentogo(tmp_path):
    """The games that KentoGo did not analyze are left out."""
    games, _skipped = collect_games(write_games(tmp_path / "games"), ExtractSettings())
    ours = kentogo_games(games, lambda path: path.name == "a.sgf")
    assert [path.name for path, _result in ours] == ["a.sgf"]
    assert trial_problems(ours, TRIAL_LOSS) == []


def test_punishment_problems_beyond_the_problems_of_a_game(tmp_path):
    """The punishment problems beyond the problems of a game are asked too."""
    none = ExtractSettings(problems_per_game=0)
    games, _skipped = collect_games(write_games(tmp_path / "games"), none)
    assert [problem.punishment for problem in trial_problems(games, TRIAL_PUNISH)] == ["punish"]
    assert trial_problems(games, TRIAL_LOSS) == []


def test_analyzed_by_kentogo_file(tmp_path):
    """Only a game whose root has KGM[KentoGo] is analyzed by KentoGo; a broken file is not."""
    kentogo, katrain, broken = tmp_path / "k.sgf", tmp_path / "t.sgf", tmp_path / "x.sgf"
    kentogo.write_text("(;SZ[19]KGM[KentoGo];B[pd])", encoding="utf-8")
    katrain.write_text("(;SZ[19];B[pd])", encoding="utf-8")
    broken.write_text("(;SZ[19", encoding="utf-8")
    assert [analyzed_by_kentogo_file(path) for path in (kentogo, katrain, broken)] == [True, False, False]


def test_load_trial(tmp_path, monkeypatch):
    """The trial asks all the problems of the kind, tells that it is a trial, and has no limit or reviews."""
    folder = write_games(tmp_path / "games")
    monkeypatch.setattr(quiz_trial, "analyzed_by_kentogo_file", lambda _path: True)
    settings = AppSettings(quiz=QuizSettings(games_folder=str(folder)))
    trial = load_trial(tmp_path / "settings.json", None, settings, TRIAL_PUNISH)
    assert [problem.punishment for problem in trial.problems] == ["punish"]
    assert (trial.new_count, trial.review_count, trial.session_limit, trial.message) == (1, 0, None, None)
    assert "1" in notice_text(trial.notices[-1])


def test_load_trial_without_problems(tmp_path, monkeypatch):
    """Without problems, the trial tells the folder, the games read and those analyzed by KentoGo."""
    folder = write_games(tmp_path / "games")
    monkeypatch.setattr(quiz_trial, "analyzed_by_kentogo_file", lambda path: path.name == "b.sgf")
    settings = AppSettings(quiz=QuizSettings(games_folder=str(folder)))
    trial = load_trial(tmp_path / "settings.json", None, settings, TRIAL_PUNISH)
    assert trial.problems == [] and trial.notices == []
    message = notice_text(trial.message)
    assert str(folder) in message and "棋譜 2 局のうち" in message and "KentoGoで解析した棋譜は 1 局" in message


def test_the_test_quiz_option():
    """--test-quiz takes the kind of the trial; without it there is no trial."""
    assert parse_arguments(["--test-quiz", "punish"]).test_quiz == "punish"
    assert parse_arguments([]).test_quiz is None
