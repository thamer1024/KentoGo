"""Make queries for KataGo's analysis engine, and read numbers from its answers.

The points lost by a move are calculated in the same way as KaTrain does
(KaTrain 1.20.0, GameNode.points_lost): the score of the position before the
move minus the score of the position after it, seen from the player of the move.
So a problem needs two analyses for each move: before it and after it.

Scores are always reported from black's side ("reportAnalysisWinratesAs": "BLACK"),
the same setting that KaTrain forces.
"""

from __future__ import annotations

from kentogo.common.rules import normalize_rules
from kentogo.common.types import Move, Position

# Settings that every query uses, the same as KaTrain.
FORCED_SETTINGS = {"reportAnalysisWinratesAs": "BLACK"}


def position_query(
    position: Position,
    extra_moves: tuple[Move, ...] = (),
    max_visits: int = 500,
    wide_root_noise: float | None = None,
) -> dict:
    """Make a query that analyzes a position, after playing some more moves on it.

    Args:
        position: The position.
        extra_moves: Moves to play after the position (for example, the answer).
        max_visits: How many positions KataGo reads.
        wide_root_noise: KaTrain's "wide_root_noise" setting, or None to use KataGo's own setting.

    Returns:
        The query, without "id" (KataGoProcess.query adds it).
    """
    moves = position.moves + extra_moves
    first_player = moves[0].color if moves else position.next_color
    settings = dict(FORCED_SETTINGS)
    if wide_root_noise is not None:
        settings["wideRootNoise"] = wide_root_noise
    return {
        "rules": normalize_rules(position.rules),
        "komi": position.komi,
        "boardXSize": position.size,
        "boardYSize": position.size,
        "initialStones": [[stone.color, stone.gtp()] for stone in position.setup],
        "initialPlayer": first_player,
        "moves": [[move.color, move.gtp()] for move in moves],
        "analyzeTurns": [len(moves)],
        "maxVisits": max_visits,
        "overrideSettings": settings,
    }


def root_score(answer: dict) -> float:
    """Return the score lead of the analyzed position, from black's side.

    Args:
        answer: KataGo's final answer to a query.

    Raises:
        ValueError: If the answer is an error, or has no score.
    """
    if "error" in answer:
        raise ValueError(f"KataGo could not analyze the position: {answer['error']}")
    try:
        return float(answer["rootInfo"]["scoreLead"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"KataGo's answer has no score: {answer}") from error


def best_sequence(answer: dict) -> tuple[str, ...]:
    """Return KataGo's predicted sequence from the analyzed position.

    It is the sequence ("pv") of the move that KataGo ranks first ("order": 0).

    Args:
        answer: KataGo's final answer to a query.

    Returns:
        The points of the sequence in GTP coordinates, or () if the answer has none.
    """
    move_infos = answer.get("moveInfos") or []
    if not move_infos:
        return ()
    best = min(move_infos, key=lambda info: info.get("order", 0))
    return tuple(best.get("pv", ()))


def best_move_score(answer: dict) -> float | None:
    """Return the score lead after KataGo's best move (the one ranked first), from black's side.

    Args:
        answer: KataGo's final answer to a query.

    Returns:
        The score, or None if the answer has no moves.
    """
    move_infos = answer.get("moveInfos") or []
    if not move_infos:
        return None
    best = min(move_infos, key=lambda info: info.get("order", 0))
    score = best.get("scoreLead")
    return float(score) if score is not None else None


def points_lost(color: str, score_before: float, score_after: float) -> float:
    """Return the points lost by a move, as KaTrain calculates them.

    Args:
        color: The player of the move, "B" or "W".
        score_before: Score lead from black's side, before the move.
        score_after: Score lead from black's side, after the move.

    Returns:
        The points lost by the player of the move. It can be a little below 0,
        because the analysis is not perfect.
    """
    sign = 1 if color == "B" else -1
    return sign * (score_before - score_after)


def with_ownership(query: dict) -> dict:
    """Return a query that also asks for the owner of each point ("includeOwnership")."""
    return {**query, "includeOwnership": True}


def ownership_map(answer: dict, size: int) -> dict[tuple[int, int], float]:
    """Return the owner of each point from an answer with ownership, from black's side (1: black, -1: white).

    KataGo lists the points row by row from the top row, so (x, y) with y = 0 at the bottom
    (the first line, as in Move) is at index (size - 1 - y) * size + x.

    Raises:
        ValueError: If the answer has no ownership of the right length.
    """
    values = answer.get("ownership")
    if not isinstance(values, list) or len(values) != size * size:
        raise ValueError("KataGo's answer has no ownership")
    return {(x, y): float(values[(size - 1 - y) * size + x]) for x in range(size) for y in range(size)}
