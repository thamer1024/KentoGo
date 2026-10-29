"""Turn problems into JSON-friendly dicts and back, to keep them in the problem cache.

Moves are written as one short text: the color and the GTP point, such as
"BQ16" or "Wpass", so that a game of 300 moves stays small.
"""

from __future__ import annotations

import functools

from kentogo.common.types import Move, Position
from kentogo.mistakes.extract import ExtractResult
from kentogo.mistakes.problem import Problem, Variation


def move_text(move: Move) -> str:
    """Return a move as a short text, such as "BQ16"."""
    return f"{move.color}{move.gtp()}"


@functools.cache
def move_from_text(text: str) -> Move:
    """Make a move from a text made by move_text.

    The results are remembered: there are only a few hundred different moves,
    and a cache with thousands of problems has hundreds of thousands of moves.
    Moves cannot be changed, so the same Move can be shared.
    """
    return Move.from_gtp(text[1:], text[0])


def problem_to_dict(problem: Problem) -> dict:
    """Return a problem as a dict of texts, numbers and lists."""
    position = problem.position
    return {
        "problem_id": problem.problem_id,
        "sgf_path": problem.sgf_path,
        "move_number": problem.move_number,
        "size": position.size,
        "komi": position.komi,
        "rules": position.rules,
        "setup": [move_text(move) for move in position.setup],
        "moves": [move_text(move) for move in position.moves],
        "next_color": position.next_color,
        "actual_move": move_text(problem.actual_move),
        "best_move": move_text(problem.best_move) if problem.best_move else None,
        "points_lost": problem.points_lost,
        "variations": [
            {"moves": [move_text(move) for move in v.moves], "source": v.source, "comment": v.comment}
            for v in problem.variations
        ],
        "notes": problem.notes,
        "candidate_losses": [[point, loss] for point, loss in problem.candidate_losses],
        "ai_comment": problem.ai_comment,
    }


def problem_from_dict(values: dict) -> Problem:
    """Make a problem from a dict made by problem_to_dict.

    Raises:
        KeyError, ValueError: If the dict is not complete or has wrong values.
    """
    position = Position(
        size=values["size"],
        komi=values["komi"],
        rules=values["rules"],
        setup=tuple(move_from_text(text) for text in values["setup"]),
        moves=tuple(move_from_text(text) for text in values["moves"]),
        next_color=values["next_color"],
    )
    best = values["best_move"]
    return Problem(
        problem_id=values["problem_id"],
        sgf_path=values["sgf_path"],
        move_number=values["move_number"],
        position=position,
        actual_move=move_from_text(values["actual_move"]),
        best_move=move_from_text(best) if best else None,
        points_lost=values["points_lost"],
        variations=tuple(
            Variation(tuple(move_from_text(text) for text in v["moves"]), v["source"], v["comment"])
            for v in values["variations"]
        ),
        notes=values["notes"],
        # Copies saved before candidate losses were kept have none.
        candidate_losses=tuple((point, float(loss)) for point, loss in values.get("candidate_losses", [])),
        ai_comment=values.get("ai_comment", ""),  # Copies saved before the AI commentary was read have none.
    )


def result_to_dict(result: ExtractResult) -> dict:
    """Return the result of one game (its problems, or why it has none) as a dict."""
    return {
        "my_color": result.my_color,
        "problems": [problem_to_dict(problem) for problem in result.problems],
        "reason": result.reason,
    }


def result_from_dict(values: dict) -> ExtractResult:
    """Make the result of one game from a dict made by result_to_dict."""
    problems = tuple(problem_from_dict(problem) for problem in values["problems"])
    return ExtractResult(values["my_color"], problems, values["reason"])
