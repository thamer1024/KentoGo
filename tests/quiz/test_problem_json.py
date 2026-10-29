"""Tests for kentogo.quiz.problem_json."""

import json
from dataclasses import replace

from kentogo.common.types import Move, Position
from kentogo.mistakes.extract import ExtractResult
from kentogo.mistakes.problem import Problem, Variation
from kentogo.quiz.problem_json import (
    move_from_text,
    move_text,
    problem_from_dict,
    problem_to_dict,
    result_from_dict,
    result_to_dict,
)


def gtp(point: str, color: str = "B") -> Move:
    """Make a move from GTP coordinates."""
    return Move.from_gtp(point, color)


PROBLEM = Problem(
    problem_id="0123456789abcdef",
    sgf_path="/games/対局 1.sgf",
    move_number=3,
    position=Position(19, 6.5, "japanese", (gtp("D4"),), (gtp("Q16", "W"), gtp("pass")), "W"),
    actual_move=gtp("A19", "W"),
    best_move=gtp("Q4", "W"),
    points_lost=8.4,
    variations=(Variation((gtp("Q4", "W"), gtp("D16")), "katrain", "note"),),
    notes="黒D17で左上を守ります。",
)


def test_moves():
    """Moves, also passes, are short texts and come back the same."""
    assert move_text(gtp("Q16", "W")) == "WQ16"
    assert move_text(gtp("pass")) == "Bpass"
    for move in (gtp("Q16", "W"), gtp("pass"), gtp("A1")):
        assert move_from_text(move_text(move)) == move


def test_result_comes_back_the_same_through_json():
    """A result with problems, and one without, are the same after JSON and back."""
    for result in (ExtractResult("W", (PROBLEM,)), ExtractResult(None, (), "unknown_color")):
        text = json.dumps(result_to_dict(result), ensure_ascii=False)
        assert result_from_dict(json.loads(text)) == result


def test_problem_without_best_move():
    """A problem without a best move comes back without it."""
    result = ExtractResult("W", (replace(PROBLEM, best_move=None),))
    assert result_from_dict(result_to_dict(result)) == result


def test_candidate_losses_and_older_copies():
    """Candidate losses come back the same, and a copy saved before they were kept has none."""
    problem = replace(PROBLEM, candidate_losses=(("Q4", 0.0), ("R4", 1.5)))
    assert problem_from_dict(json.loads(json.dumps(problem_to_dict(problem)))) == problem
    older = problem_to_dict(PROBLEM)
    del older["candidate_losses"]
    assert problem_from_dict(older).candidate_losses == ()


def test_ai_comment_and_older_copies():
    """The AI commentary comes back the same, and a copy saved before it was kept has none."""
    problem = replace(PROBLEM, ai_comment="黒D17が大きいです。")
    assert problem_from_dict(json.loads(json.dumps(problem_to_dict(problem)))) == problem
    older = problem_to_dict(PROBLEM)
    del older["ai_comment"]
    assert problem_from_dict(older).ai_comment == ""
