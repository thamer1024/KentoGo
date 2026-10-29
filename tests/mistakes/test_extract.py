"""Tests for kentogo.mistakes.extract."""

import base64
import gzip
import json

import pytest
from pysgf import GoGame

from kentogo.common.types import Move
from kentogo.mistakes.extract import REASON_UNKNOWN_COLOR, ExtractSettings, extract_problems
from kentogo.record.ai_comment import AI_HEADER
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def katrain_comment(
    number: int, color: str, point: str, loss: float | None, best: str, pv: str, undone: bool = False
) -> str:
    """Make a comment in the same form as KaTrain's English comments."""
    text = f"\nMove {number}: {color} {point}\nScore: B+0.5\n"
    if loss is None:
        text += "Move was predicted best move\n"
    else:
        text += f"Estimated point loss: {loss:.1f}\nPredicted top move was {best} (B+1.0).\n"
    text += f"PV: {pv}\n"
    if undone:
        text += "Move was automatically undone in teaching mode.\nPredicted follow-up: WD16\n"
    return text + INTERNAL_MARKER


# Branches next to black's move 5: a move taken back by KaTrain, and a move tried by the user.
UNDONE_BRANCHES = (
    f"(;B[ba]C[{katrain_comment(5, 'B', 'B19', 20.0, 'Q4', 'BQ4', undone=True)}])"
    f"(;B[ca]C[{katrain_comment(5, 'B', 'C19', 30.0, 'Q4', 'BQ4')}])"
)


def game(black: str = HUMAN, white: str = AI, notes: str = "", branches: str = "") -> str:
    """Make a small game. Black's moves 3, 5 and 7 lose 8.0, 2.0 and 12.0 points.

    branches are added as other moves next to black's move 5.
    """
    noted = notes + "\n" + SEPARATOR if notes else ""
    nodes = [
        f";B[pd]C[{katrain_comment(1, 'B', 'Q16', None, 'Q16', 'BQ16 D4')}]",
        f";W[dp]C[{katrain_comment(2, 'W', 'D4', 4.0, 'D16', 'WD16 Q4')}]",
        f";B[aa]C[{noted}{katrain_comment(3, 'B', 'A19', 8.0, 'Q4', 'BQ4 D16 C17')}]",
        f";W[dd]C[{katrain_comment(4, 'W', 'D16', None, 'D16', 'WD16')}]",
    ]
    rest = [
        f";B[ab]C[{katrain_comment(5, 'B', 'A18', 2.0, 'Q4', 'BQ4')}]",
        f";W[pp]C[{katrain_comment(6, 'W', 'Q4', None, 'Q4', 'WQ4')}]",
        f";B[ac]C[{katrain_comment(7, 'B', 'A17', 12.0, 'R16', 'BR16 Q17')}]",
    ]
    main = "".join(rest)
    tail = f"(;{main[1:]}){branches}" if branches else main
    return f"(;SZ[19]KM[6.5]RU[japanese]PB[{black}]PW[{white}]{''.join(nodes)}{tail})"


def extract(text: str, **settings):
    """Read an SGF text and make problems from it."""
    return extract_problems(GoGame.parse_sgf(text), "game.sgf", ExtractSettings(**settings))


def test_problems_are_the_users_big_mistakes():
    """Only the user's moves with a loss of at least 3 points are used, the largest first."""
    result = extract(game())
    assert result.my_color == "B"
    assert [(p.move_number, p.points_lost) for p in result.problems] == [(7, 12.0), (3, 8.0)]


def test_problem_contents():
    """A problem has the position before the mistake, the mistake, the best move and KaTrain's sequence."""
    problem = extract(game()).problems[1]
    assert problem.sgf_path == "game.sgf"
    assert problem.position.next_color == "B"
    assert [m.gtp() for m in problem.position.moves] == ["Q16", "D4"]
    assert problem.actual_move == Move.from_gtp("A19", "B")
    assert problem.best_move == Move.from_gtp("Q4", "B")
    sequence = problem.variations[0]
    assert sequence.source == "katrain"
    assert [(m.color, m.gtp()) for m in sequence.moves] == [("B", "Q4"), ("W", "D16"), ("B", "C17")]


def test_notes_are_kept():
    """The user's notes on the mistake are kept in the problem."""
    problem = extract(game(notes="Claude: too small")).problems[1]
    assert problem.notes == "Claude: too small"


def test_user_playing_white():
    """When the user plays white, white's moves are used."""
    result = extract(game(black=AI, white=HUMAN))
    assert result.my_color == "W"
    assert [p.move_number for p in result.problems] == [2]


def test_settings():
    """The number of problems, the minimum loss and the skipped opening can be set."""
    assert [p.move_number for p in extract(game(), problems_per_game=1).problems] == [7]
    assert [p.move_number for p in extract(game(), min_points_lost=1.0).problems] == [7, 3, 5]
    assert [p.move_number for p in extract(game(), skip_opening_moves=3).problems] == [7]


def test_my_names():
    """A name in my_names decides the user's color."""
    result = extract(game(black="opponent", white="Taro"), my_names=("Taro",))
    assert result.my_color == "W"


def test_unknown_color():
    """No problems are made when the user's color is not found."""
    result = extract(game(black=HUMAN, white=HUMAN))
    assert (result.my_color, result.problems, result.reason) == (None, (), REASON_UNKNOWN_COLOR)


def test_color_from_rank_and_file_name():
    """When both players are "Human", the rank or the file name made by KaTrain finds the color."""
    both_human = game(black=HUMAN, white=HUMAN)
    with_rank = both_human.replace("PB[", "BR[20k]PB[", 1)
    assert extract(with_rank).my_color == "W"
    file_name = "KaTrain_AI (Human-like) vs Human (Normal Game) 2026-10-12 05 07 05.sgf"
    result = extract_problems(GoGame.parse_sgf(both_human), file_name, ExtractSettings())
    assert result.my_color == "W"


def test_comment_about_another_move_is_ignored():
    """A comment that does not match the move of its node is not trusted."""
    text = game().replace("Move 7: B A17", "Move 7: B A16")
    assert [p.move_number for p in extract(text).problems] == [3]


def test_undone_moves_are_not_used_when_the_setting_is_off():
    """Moves taken back by KaTrain are not used unless include_undone_moves is on."""
    result = extract(game(branches=UNDONE_BRANCHES))
    assert [p.move_number for p in result.problems] == [7, 3]


def test_undone_moves_are_used_when_the_setting_is_on():
    """A move taken back by KaTrain becomes a problem, but a move tried by the user does not."""
    result = extract(game(branches=UNDONE_BRANCHES), include_undone_moves=True)
    assert [(p.move_number, p.actual_move.gtp()) for p in result.problems] == [(5, "B19"), (7, "A17"), (3, "A19")]
    assert [m.gtp() for m in result.problems[0].position.moves] == ["Q16", "D4", "A19", "D16"]


def test_main_line_move_wins_in_the_same_position():
    """If a taken-back move and a main line move are in the same position, the main line move is used."""
    result = extract(game(branches=UNDONE_BRANCHES), include_undone_moves=True, min_points_lost=1.0)
    same_position = [p for p in result.problems if p.move_number == 5]
    assert [p.actual_move.gtp() for p in same_position] == ["A18"]


def test_settings_from_and_to_dict():
    """Settings are read from a dict, and written back to the same dict."""
    values = {
        "my_names": ["Taro"],
        "problems_per_game": 3,
        "min_points_lost": 2.5,
        "skip_opening_moves": 10,
        "include_undone_moves": True,
        "decided_winrate": 97.0,
        "decided_lead": 30.0,
    }
    settings = ExtractSettings.from_dict(values)
    assert settings == ExtractSettings(("Taro",), 3, 2.5, 10, True, 97.0, 30.0)
    assert settings.to_dict() == values


def test_settings_from_dict_with_missing_and_unknown_keys():
    """Missing keys get the default values, and unknown keys are ignored."""
    assert ExtractSettings.from_dict({"unknown": 1}) == ExtractSettings()


@pytest.mark.parametrize("values", [{"problems_per_game": "many"}, {"include_undone_moves": "false"}])
def test_settings_from_dict_with_wrong_values(values):
    """A value with a wrong type is an error, so that a broken settings file is noticed."""
    with pytest.raises(ValueError):
        ExtractSettings.from_dict(values)


def kt_property(analysis: dict) -> str:
    """Make a KT property in the same way as KaTrain (analysis_dumps)."""
    parts = [b"\x00" * 8, b"\x00" * 8, json.dumps(analysis).encode("utf-8")]
    return "KT" + "".join(f"[{base64.standard_b64encode(gzip.compress(part)).decode()}]" for part in parts)


def test_candidate_losses_from_katrain_analysis_data():
    """With KaTrain's analysis data on the node before the mistake, the candidate losses are kept."""
    analysis = {"root": {"scoreLead": 3.0}, "moves": {"Q4": {"scoreLead": 3.0}, "R4": {"scoreLead": 1.5}}}
    text = game().replace(";W[dp]C[", f";W[dp]{kt_property(analysis)}C[", 1)  # The node before move 3.
    problem = next(p for p in extract(text).problems if p.move_number == 3)
    assert problem.candidate_losses == (("Q4", 0.0), ("R4", 1.5))


def test_broken_analysis_data_is_ignored():
    """Broken analysis data does not stop the problem from being made."""
    text = game().replace(";W[dp]C[", ";W[dp]KT[a][b][c]C[", 1)
    problem = next(p for p in extract(text).problems if p.move_number == 3)
    assert problem.candidate_losses == ()


def test_ai_commentary_is_kept_apart_from_the_notes():
    """The AI commentary written by the commentary tool is not mixed with the user's notes."""
    comment = f"{AI_HEADER}\nA19 is too small.\n{SEPARATOR}\nmy note"
    problem = extract(game(notes=comment)).problems[1]
    assert (problem.ai_comment, problem.notes) == ("A19 is too small.", "my note")


def test_moves_in_decided_positions_wait():
    """A mistake made when the game was already decided is used only when there are not enough other problems."""
    decided = {"root": {"winrate": 0.995, "scoreLead": 30.0}, "moves": {}}
    text = game().replace(";W[pp]C[", f";W[pp]{kt_property(decided)}C[", 1)  # The node before move 7.
    assert [p.move_number for p in extract(text, problems_per_game=1).problems] == [3]  # Move 7 lost more.
    assert sorted(p.move_number for p in extract(text, problems_per_game=2).problems) == [3, 7]


def test_decided_position_thresholds_are_settings():
    """With higher thresholds, the same position is not decided."""
    decided = {"root": {"winrate": 0.995, "scoreLead": 30.0}, "moves": {}}
    text = game().replace(";W[pp]C[", f";W[pp]{kt_property(decided)}C[", 1)
    result = extract(text, problems_per_game=1, decided_winrate=99.9, decided_lead=50.0)
    assert [p.move_number for p in result.problems] == [7]
