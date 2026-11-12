"""Tests for kentogo.mistakes.extract."""

import base64
import gzip
import json

import pytest
from pysgf import GoGame

from kentogo.common.sgf import main_line, node_move
from kentogo.common.types import Move
from kentogo.mistakes.extract import (
    PUNISH,
    REASON_UNKNOWN_COLOR,
    SHARED,
    ExtractSettings,
    PunishmentChance,
    _undone_moves,
    extract_problems,
    first_of_each_best_move,
    punishment_chances,
)
from kentogo.record.ai_comment import AI_HEADER
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR
from kentogo.record.kentogo_analysis import KGA_PROPERTY, encode_kga

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


def test_move_losses_are_all_the_users_main_line_moves():
    """The loss of each of the user's moves is kept for the report, also the moves that are not problems."""
    assert extract(game(branches=UNDONE_BRANCHES)).move_losses == (8.0, 2.0, 12.0)  # Branches do not count.
    assert extract(game(), problems_per_game=1).move_losses == (8.0, 2.0, 12.0)


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


def test_the_moves_of_the_game_after_a_problem_are_kept():
    """The game move and the moves after it, at most GAME_LINE_MOVES (the game ends after move 7)."""
    problems = extract(game()).problems
    assert [m.gtp() for m in problems[1].game_line] == ["A19", "D16", "A18", "Q4", "A17"]
    assert problems[0].game_line == ()  # The last move of the game has no moves after it.


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
        "loss_stages": [],
        "punish_opponent_loss": 20.0,
        "punish_my_loss": 4.0,
    }
    settings = ExtractSettings.from_dict(values)
    assert settings == ExtractSettings(("Taro",), 3, 2.5, 10, True, 97.0, 30.0, (), 20.0, 4.0)
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


def test_candidate_losses_from_kentogos_own_analysis_data():
    """KentoGo's KGA is read in the same way as KaTrain's KT, and comes before it on the same node."""
    analysis = {"root": {"scoreLead": 3.0}, "moves": {"Q4": {"scoreLead": 3.0}, "R4": {"scoreLead": 1.5}}}
    old = {"root": {"scoreLead": 3.0}, "moves": {"Q4": {"scoreLead": 3.0}, "R4": {"scoreLead": -9.0}}}
    kga = KGA_PROPERTY + "".join(f"[{value}]" for value in encode_kga(analysis))
    text = game().replace(";W[dp]C[", f";W[dp]{kga}{kt_property(old)}C[", 1)
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


def test_loss_stages():
    """With stages, every mistake of at least the smallest stage is a problem, without the limit per game.

    Move 5 (2.0 points) has the same best move as move 3 (Q4), so only move 3 is kept.
    """
    result = extract(game(), problems_per_game=1, min_points_lost=10.0, loss_stages=(9.0, 2.0))
    assert [p.move_number for p in result.problems] == [7, 3]
    assert [p.move_number for p in extract(game(), loss_stages=(12.0, 9.0)).problems] == [7]


def test_loss_stages_setting():
    """The stages are kept as a list of numbers, the biggest first; the smallest is the smallest loss."""
    settings = ExtractSettings.from_dict({"loss_stages": [5, 20, 10, 5]})
    assert settings.loss_stages == (20.0, 10.0, 5.0)
    assert settings.smallest_loss() == 5.0
    assert ExtractSettings.from_dict(settings.to_dict()) == settings
    assert ExtractSettings().smallest_loss() == 3.0
    for wrong in ([0], [-5], "20,10"):
        with pytest.raises(ValueError):
            ExtractSettings.from_dict({"loss_stages": wrong})


BEFORE_MOVE_3 = {  # The analysis of the node before move 3 (KaTrain's comment says 8 points and Q4).
    "root": {"scoreLead": 3.0},
    "moves": {"D16": {"scoreLead": 3.0, "order": 0, "pv": ["D16", "Q4"]}, "Q4": {"scoreLead": 2.5, "order": 1}},
}
AFTER_MOVE_3 = {"root": {"scoreLead": -9.0}}  # Black lost 12 points with A19.


def with_analysis_of_move_3(text: str) -> str:
    """Add the analysis data of move 3 and of the node before it to a game made by game()."""
    text = text.replace(";W[dp]C[", f";W[dp]{kt_property(BEFORE_MOVE_3)}C[", 1)
    return text.replace(";B[aa]C[", f";B[aa]{kt_property(AFTER_MOVE_3)}C[", 1)


def test_analysis_data_comes_before_the_comment():
    """With analysis data on the move and the node before it, the loss, best move and sequence come from it."""
    problem = next(p for p in extract(with_analysis_of_move_3(game())).problems if p.move_number == 3)
    assert problem.points_lost == 12.0
    assert problem.best_move.gtp() == "D16"
    assert [move.gtp() for move in problem.variations[0].moves] == ["D16", "Q4"]


def test_analysis_data_without_a_comment():
    """A move with analysis data but no comment from KaTrain still becomes a problem."""
    text = f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd];W[dp]{kt_property(BEFORE_MOVE_3)};B[aa]{kt_property(AFTER_MOVE_3)})"
    assert [(p.move_number, p.points_lost) for p in extract(text).problems] == [(3, 12.0)]


def test_comment_is_used_when_the_analysis_data_cannot_be_used():
    """Broken data on the move, or a version that is too new, falls back to KaTrain's comment (8 points)."""
    broken = game().replace(";W[dp]C[", f";W[dp]{kt_property(BEFORE_MOVE_3)}C[", 1)
    broken = broken.replace(";B[aa]C[", ";B[aa]KT[a][b][c]C[", 1)
    newer = with_analysis_of_move_3(game()).replace("(;", "(;KTV[9.0]", 1)
    for text in (broken, newer):
        problem = next(p for p in extract(text).problems if p.move_number == 3)
        assert (problem.points_lost, problem.best_move.gtp()) == (8.0, "Q4")


KENTOGO_BEFORE_MOVE_3 = {  # The position before move 3 analyzed in KentoGo's mode: A19 read there too.
    "root": {"scoreLead": 2.8},
    "moves": {
        "D16": {"scoreLead": 3.0, "order": 0, "pv": ["D16", "Q4"]},
        "Q4": {"scoreLead": 2.5, "order": 1},
        "A19": {"scoreLead": -10.0, "order": 999},
    },
}


def test_kentogo_mode_losses_come_from_the_best_move_in_the_position_before():
    """With KGM[KentoGo], A19 lost 13 points against D16 there (KaTrain's way: 2.8 - (-9.0) = 11.8)."""
    text = game().replace(";W[dp]C[", f";W[dp]{kt_property(KENTOGO_BEFORE_MOVE_3)}C[", 1)
    text = text.replace(";B[aa]C[", f";B[aa]{kt_property(AFTER_MOVE_3)}C[", 1)
    katrain = next(p for p in extract(text).problems if p.move_number == 3)
    kentogo = next(p for p in extract(text.replace("(;", "(;KGM[KentoGo]", 1)).problems if p.move_number == 3)
    assert (katrain.points_lost, kentogo.points_lost) == (11.8, 13.0)
    assert dict(katrain.candidate_losses)["Q4"] == pytest.approx(0.3)  # From the root's score.
    assert dict(kentogo.candidate_losses)["Q4"] == pytest.approx(0.5)  # From the best move.
    assert dict(kentogo.candidate_losses)["D16"] == 0.0
    assert katrain.variations[0].source == "katrain" and kentogo.variations[0].source == "kentogo"


def chances(text: str, opponent_loss: float, my_loss: float, **settings) -> list:
    return punishment_chances(GoGame.parse_sgf(text), "game.sgf", ExtractSettings(**settings), opponent_loss, my_loss)


def test_punishment_chances():
    """White's move 2 lost 4 points and black's move 3 then lost 8: black did not punish it."""
    [chance] = chances(game(), 3.0, 5.0)
    assert (chance.move_number, chance.opponent_move.gtp(), chance.opponent_loss) == (3, "D4", 4.0)
    assert (chance.my_move.gtp(), chance.my_loss, chance.best_move) == ("A19", 8.0, "Q4")
    assert (chance.opponent_best, chance.kind, chance.decided) == ("D16", PUNISH, False)
    assert chances(game(), 5.0, 5.0) == []  # The opponent's mistake was smaller.
    assert chances(game(), 3.0, 9.0) == []  # The user's move lost less.
    assert chances(game(), 0.0, 0.0)[-1].move_number == 3  # After the opponent's best moves (no loss known): none.


def test_punishment_chances_for_white_and_without_a_color():
    """The user's color decides whose mistakes are the opponent's; without it there are none."""
    assert chances(game(black=AI, white=HUMAN), 0.0, 0.0) == []  # Black's moves follow white's best moves.
    assert chances(game(black="x", white="y"), 0.0, 0.0) == []


def test_punishment_chance_in_a_decided_position_is_marked():
    """The position before the opponent's mistake tells whether the game was decided, not the one after it."""
    decided = {"root": {"winrate": 0.995, "scoreLead": 30.0}, "moves": {}}
    text = game().replace(";B[pd]C[", f";B[pd]{kt_property(decided)}C[", 1)  # The position before white's move 2.
    assert chances(text, 3.0, 5.0)[0].decided
    after = game().replace(";W[dp]C[", f";W[dp]{kt_property(decided)}C[", 1)  # After white's mistake.
    assert not chances(after, 3.0, 5.0)[0].decided


def handicap_game(start_lead: float, lead: float) -> str:
    """The small game with a handicap stone: black leads by start_lead at the start and by lead before move 7."""
    start = {"root": {"winrate": 0.9, "scoreLead": start_lead}, "moves": {}}
    before = {"root": {"winrate": 0.995, "scoreLead": lead}, "moves": {}}
    text = game().replace(";W[pp]C[", f";W[pp]{kt_property(before)}C[", 1)
    return text.replace("RU[japanese]", f"RU[japanese]AB[jj]{kt_property(start)}", 1)


def test_a_handicap_game_is_decided_by_the_lead_gained_since_the_start():
    """With handicap stones, the winrate is not used, and the lead counts from the lead at the start."""
    open_game = extract(handicap_game(18.0, 45.0), problems_per_game=1)  # 27 points gained: not decided.
    assert [p.move_number for p in open_game.problems] == [7]
    decided = extract(handicap_game(0.0, 45.0), problems_per_game=1)  # 45 points gained: decided.
    assert [p.move_number for p in decided.problems] == [3]


def chance(number: int, best: str | None, opponent_best: str | None = "K10") -> PunishmentChance:
    move = Move.from_gtp("A1", "B")
    return PunishmentChance(number, Move.from_gtp("A2", "W"), 12.0, move, 8.0, best, opponent_best)


def test_kinds_and_only_the_first_moment_of_each_best_move():
    """Both missing the same point is "shared"; when they keep missing it, only the first moment counts."""
    assert (chance(3, "C3").kind, chance(3, "K10").kind, chance(3, None, None).kind) == (PUNISH, SHARED, PUNISH)
    kept = first_of_each_best_move(
        [chance(3, "H3"), chance(5, "H3"), chance(7, "C3"), chance(9, None), chance(11, None)]
    )
    assert [item.move_number for item in kept] == [3, 7, 9, 11]


def test_problems_know_the_opponent_move_before_them():
    """Move 3 follows white's move 2 (4 points lost, best D16): with low thresholds it is a punishment problem."""
    problem = next(p for p in extract(game()).problems if p.move_number == 3)
    assert (problem.opponent_loss, problem.opponent_best, problem.punishment) == (4.0, "D16", "")  # Below 15.
    low = next(p for p in extract(game(), punish_opponent_loss=4.0).problems if p.move_number == 3)
    assert low.punishment == PUNISH
    first = next(p for p in extract(game()).problems if p.move_number == 7)  # After white's best move (no loss).
    assert (first.opponent_loss, first.punishment) == (None, "")


def test_punishment_problems_beyond_the_problems_of_a_game_are_kept_apart():
    """With one problem a game, move 7 (12 points) is the problem; the punishment problem 3 is kept apart."""
    result = extract(game(), problems_per_game=1, punish_opponent_loss=4.0)
    assert [p.move_number for p in result.problems] == [7]
    assert [(p.move_number, p.punishment) for p in result.punishments] == [(3, PUNISH)]
    assert extract(game(), punish_opponent_loss=4.0).punishments == ()  # Move 3 is a problem already.


def left_again() -> str:
    """The game, but white's move 4 is D17 (5 points lost, best D16): the same best move as at its move 2."""
    text = game().replace(";W[dd]C[", ";W[dc]C[", 1)
    return text.replace(
        katrain_comment(4, "W", "D16", None, "D16", "WD16"), katrain_comment(4, "W", "D17", 5.0, "D16", "WD16")
    )


def test_the_same_point_left_again_is_no_punishment():
    """Black's move 5 follows white's D17, but white's best move D16 was already its best at move 2."""
    low = {"punish_opponent_loss": 3.0, "punish_my_loss": 1.0, "min_points_lost": 1.0}
    problem = next(p for p in extract(left_again(), **low).problems if p.move_number == 5)
    assert (problem.opponent_loss, problem.opponent_best, problem.punishment) == (5.0, "D16", "")
    first = next(p for p in extract(left_again(), **low).problems if p.move_number == 3)
    assert first.punishment == PUNISH  # The first time white left D16 counts.
    assert [c.move_number for c in chances(left_again(), 3.0, 1.0)] == [3]


def test_a_move_taken_back_is_found_from_kentogos_analysis_data():
    """A branch whose KGA says "taken_back" is a move that KaTrain took back (without KaTrain's comment)."""
    data = "".join(f"[{value}]" for value in encode_kga({"root": {"scoreLead": 0.0}, "moves": {}, "taken_back": True}))
    text = "(;SZ[9]PB[Human]PW[AI]KGM[KentoGo];B[cc](;W[dd];B[ee])(;W[aa]KGA" + data + "))"
    assert [m.gtp() for m in _undone(text)] == ["A9"]


def _undone(text: str) -> list:
    """The taken-back moves of a game (the moves of the branches that KaTrain took back)."""
    return [node_move(node) for node, _ in _undone_moves(main_line(GoGame.parse_sgf(text)))]
