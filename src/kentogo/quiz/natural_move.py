"""A natural and strong move of the user among the moves that a human of the user's rank may play.

The candidates are the moves that the human may play (see katago.human_moves.candidate_moves). KataGo reads only
them, and the move with the least loss is chosen; among the moves whose losses are about the same, the most likely
one (see katago.human_moves.choose_natural). So the move is one that the human may really play, and the best of
them.

Each choice is told to a log (see line_log). When the sequence has ended, KataGo reads each position without any
limit, so that the log also tells how much the chosen move lost against the best move of all (the human may have
no good move).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping

from kentogo.common.types import Move, Position
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.human_moves import Candidate, choose_natural, losses_of, move_scores, restricted_query
from kentogo.katago.queries import best_sequence, position_query, root_score


def choose_move(
    engine: AnalysisEngine,
    position: Position,
    moves: tuple[Move, ...],
    candidates: tuple[Candidate, ...],
    visits: int,
    max_time: float,
    log: Callable[[dict], None],
    defer: Callable[[Callable[[], None]], None],
    on_move: Callable[[Move], None],
    on_error: Callable[[str], None],
) -> None:
    """Choose the user's next move among the candidates, and tell it to on_move (in KataGo's thread).

    A single candidate is played without reading. Otherwise KataGo reads the candidates with `visits`.

    Args:
        engine: KataGo (the main one).
        position: The problem position.
        moves: The moves played after it.
        candidates: The moves that a human may play, from the most likely one.
        visits: How many positions KataGo reads for the candidates.
        max_time: The most seconds of each reading (0: no limit); a slow computer reads fewer positions.
        log: Called with a record about the choice, and later with one about the move against the best move.
        defer: Called with what is to be done when the sequence has ended (the reading of the position without a
            limit, which would slow down the moves of the sequence if it ran at once).
        on_move: Called with the chosen move.
        on_error: Called with what went wrong.
    """
    if len(candidates) == 1:
        log(_choice_record("only", len(moves), candidates[0], candidates, {}, 0, 0.0))
        on_move(candidates[0].move)
        return
    started = time.monotonic()
    query = restricted_query(position, moves, tuple(c.move for c in candidates), visits, max_time)

    def receive(answer: dict) -> None:
        if answer.get("isDuringSearch"):
            return
        try:
            scores = move_scores(answer)
        except ValueError as error:
            on_error(str(error))
            return
        losses = losses_of(scores, candidates[0].move.color)
        chosen = choose_natural(candidates, losses)
        how = "search"
        if chosen is None:  # KataGo read none of them.
            chosen, how = candidates[0], "fallback"
        log(_choice_record(how, len(moves), chosen, candidates, losses, visits, time.monotonic() - started))
        if how == "search":
            chosen_score = scores[chosen.move.gtp()]
            defer(lambda: _ask_reference(engine, position, moves, chosen, chosen_score, (visits, max_time), log))
        on_move(chosen.move)

    engine.query(query, receive)


def _ask_reference(
    engine: AnalysisEngine,
    position: Position,
    moves: tuple[Move, ...],
    chosen: Candidate,
    chosen_score: float,
    reading: tuple[int, float],
    log: Callable[[dict], None],
) -> None:
    """Read the position without a limit on the moves (reading: visits and max_time), and log the chosen move's loss
    against the best move of all."""
    visits, max_time = reading
    color = chosen.move.color
    number = len(moves) + 1

    def receive(answer: dict) -> None:
        if answer.get("isDuringSearch"):
            return
        try:
            best_score = root_score(answer)
        except ValueError:
            return  # The log is only for checking; the sequence does not need it.
        points = best_sequence(answer)
        sign = 1 if color == "B" else -1  # The scores are from black's side.
        log(
            {
                "event": "human_best_reference",
                "number": number,
                "color": color,
                "chosen": chosen.move.gtp(),
                "best": points[0] if points else None,
                "loss_against_best": round(max(sign * (best_score - chosen_score), 0.0), 2),
                "visits": visits,
            }
        )

    engine.query(position_query(position, moves, visits, max_time=max_time), receive)


def _choice_record(
    how: str,
    played: int,
    chosen: Candidate,
    candidates: tuple[Candidate, ...],
    losses: Mapping[str, float],
    visits: int,
    seconds: float,
) -> dict:
    """Return the log record of a choice: how it was made, from which candidates, and with which losses."""
    return {
        "event": "human_best_move",
        "number": played + 1,
        "color": chosen.move.color,
        "how": how,  # "only" (one candidate), "search" (the least loss), or "fallback" (nothing read: the likeliest).
        "chosen": chosen.move.gtp(),
        "chosen_loss": _rounded(losses.get(chosen.move.gtp())),
        "visits": visits,
        "seconds": round(seconds, 2),
        "candidates": [
            {"move": c.move.gtp(), "chance": round(c.chance, 3), "loss": _rounded(losses.get(c.move.gtp()))}
            for c in candidates
        ],
    }


def _rounded(points: float | None) -> float | None:
    """Return points rounded for the log (None stays None)."""
    return None if points is None else round(points, 2)
