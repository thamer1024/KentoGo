"""KentoGo's own readings of the moves read deeply (the deep nodes, see analysis.analyze).

They are the material of features that come later (see record.kentogo_data): KataGo's answers are
kept as they are, from black's side (scores and win rates), and nothing is concluded here.

The readings of a move (its node, and the position before it, where the player chose it):

- "pass_before": the player passes instead of the move. The difference from the best move's score
  is what the position asked for: a big difference means that something was urgent (急場); the
  opponent's best move after the pass ("next") shows where.
- "best_after": the best move is played instead (with KataGo's areas, ownership): the position that
  the played move is compared with.
- "pass_after_played" and "pass_after_best": the opponent passes after the played move, and after
  the best move. A small difference from the position after the move means that the opponent could
  leave it (the move did not make a threat: 響かない手), and the opponent's next move shows what
  the move left behind.

Each reading is asked with the visits of the deep reading. A reading that KataGo cannot answer is
asked again (retries) and then left out.
"""

from __future__ import annotations

from collections.abc import Callable

from pysgf import GoNode

from kentogo.analysis.game_analysis import Engine, GameAnalysis, NodeStep, Progress, analyze_with_retries
from kentogo.analysis.query import QuerySettings, query_after

TENUKI_STEP = "tenuki"  # The name of these readings in the progress.
PASS = "pass"


def best_move(game: GameAnalysis, node: GoNode) -> str | None:
    """Return KataGo's best move (order 0) in the position before a node, or None."""
    before = game.analysis(node.parent)
    if before is None:
        return None
    return next((values["move"] for values in before["moves"].values() if values.get("order") == 0), None)


def readings_of(game: GameAnalysis, node: GoNode) -> dict[str, list[tuple[str, str]]]:
    """Return the readings of a deep node: their names, and the moves after the position before the node."""
    move = node.move
    player, other = move.player, ("W" if move.player == "B" else "B")
    played = (player, move.gtp())
    readings = {"pass_before": [(player, PASS)], "pass_after_played": [played, (other, PASS)]}
    best = best_move(game, node)
    if best is not None and best != PASS:
        readings["best_after"] = [(player, best)]
        readings["pass_after_best"] = [(player, best), (other, PASS)]
    return readings


def read_tenuki(
    engine: Engine,
    game: GameAnalysis,
    visits: int,
    wide_root_noise: float,
    priority: int,
    progress: Progress,
    retries: int,
) -> None:
    """Ask KataGo the readings of every deep node (see the module's docstring) and keep them in game.readings."""
    settings = QuerySettings(visits, wide_root_noise, priority)
    names = ("pass_before", "pass_after_played", "best_after", "pass_after_best")
    batches = [(name, [node for node in game.deep_nodes if name in readings_of(game, node)]) for name in names]
    total = sum(len(nodes) for _, nodes in batches)
    before = 0  # The readings of the batches already done, so that the progress counts all of them together.
    for name, nodes in batches:
        step = NodeStep(_query(game, name, settings), _keep(name))
        analyze_with_retries(engine, game, nodes, step, _counted(progress, before, total), retries)
        before += len(nodes)


def _counted(progress: Progress, before: int, total: int) -> Callable[[int, int], None]:
    """Return the progress of one batch of readings, counted with the batches before it."""
    return lambda done, _batch: progress(TENUKI_STEP, min(before + done, total), total)


def _query(game: GameAnalysis, name: str, settings: QuerySettings) -> Callable[[GoNode], dict | None]:
    """Return the query of one reading for a node, from the position before it."""

    def query(node: GoNode) -> dict | None:
        found = query_after(node.parent, settings, readings_of(game, node)[name])
        if found is not None and name != "best_after":  # Only the best move's position needs the areas.
            found = {**found, "includeOwnership": False, "includeMovesOwnership": False, "includePolicy": False}
        return found

    return query


def _keep(name: str) -> Callable[[GameAnalysis, GoNode, dict], None]:
    """Return how the answer of one reading is kept."""

    def keep(game: GameAnalysis, node: GoNode, answer: dict) -> None:
        game.readings.setdefault(id(node), {})[name] = answer_values(answer)

    return keep


def answer_values(answer: dict) -> dict:
    """Return what KentoGo keeps of an answer: the score, win rate and visits of the position, KataGo's
    next move there with its sequence, and the areas (ownership) when they were asked for."""
    root = answer["rootInfo"]
    values = {key: root[key] for key in ("scoreLead", "winrate", "visits") if key in root}
    top = next((info for info in answer.get("moveInfos", []) if info.get("order") == 0), None)
    if top is not None:
        values["next"] = top["move"]
        values["pv"] = list(top.get("pv", []))
    if answer.get("ownership"):
        values["ownership"] = list(answer["ownership"])
    return values
