"""Analyze all nodes of a game with KataGo, in the same way as KaTrain.

KaTrain 1.20.0 (katrain/core/game.py) does it in two steps, and so does this module:

1. When a game is opened (Game.analyze_all_nodes), every node of the tree (branches too) that
   has no saved analysis data (KT) is analyzed with the engine's max_visits (or fast_visits),
   with the time limit, at KaTrain's priority for a game (-100). Saved analysis data is used as it is.
2. "Re-analyze game" (Game.analyze_extra, mode "game") analyzes the nodes again with more visits
   (by default the fewest visits asked for any node plus max_visits), without the time limit:
   only the mistakes when asked (the node's own move or a move after it lost more than the
   mistake threshold), and only the nodes whose depth - 1 is in the range of moves when one is given.

These are methods of KaTrain's Game class, so they are written for KentoGo with the same behavior.
Two differences make the result the same every time: KataGo's reports during the search are not
asked for (KaTrain shows them while it thinks; only the final answer is kept in the end), and the
answers are put into the analyses in the order of the tree, the node before its children,
whatever order KataGo answers in.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pysgf import GoNode

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.node_analysis import apply_answer, empty_analysis, points_lost
from kentogo.analysis.query import QuerySettings, node_query
from kentogo.record.katrain_kt import decode_kt, decode_kt_numbers

GAME_PRIORITY = -100  # KaTrain's PRIORITY_GAME_ANALYSIS.
REANALYSIS_PRIORITY = -1_000_000  # KaTrain's priority of "Re-analyze game".

FIRST_STEP = "first"  # The analysis of the nodes without saved data.
REANALYSIS_STEP = "again"  # "Re-analyze game".
END_OF_GAME = 100_000  # The end of the range of moves when move_to is 0.

Progress = Callable[[str, int, int], None]  # (step, answers received, queries sent).


class Engine(Protocol):
    """What this module needs from KataGo (KataGoProcess has it)."""

    def query(self, request: dict, callback: Callable[[dict], None]) -> str:
        """Send a query, and call callback with each answer."""
        ...


@dataclass(frozen=True)
class EngineValues:
    """The engine settings that the analysis uses (see katago.engine_settings).

    Attributes:
        max_visits: KaTrain's "max_visits".
        wide_root_noise: KaTrain's "wide_root_noise".
    """

    max_visits: int
    wide_root_noise: float


@dataclass
class GameAnalysis:
    """The analyses of all nodes of a game.

    Attributes:
        root: The root node of the game.
        analyses: The analysis of each node, by id(node) (KaTrain's analysis dicts, see node_analysis).
        visits: The visits asked for each node (KaTrain's analysis_visits_requested).
        failed: The number of queries that KataGo could not answer.
    """

    root: GoNode
    analyses: dict[int, dict] = field(default_factory=dict)
    visits: dict[int, int] = field(default_factory=dict)
    failed: int = 0

    @property
    def nodes(self) -> list[GoNode]:
        """Return all nodes of the tree, the node before its children (KaTrain's nodes_in_tree)."""
        return self.root.nodes_in_tree

    def analysis(self, node: GoNode) -> dict | None:
        """Return the analysis of a node, or None when it has none."""
        analysis = self.analyses.get(id(node))
        return analysis if analysis is not None and analysis["root"] is not None else None

    def points_lost(self, node: GoNode) -> float | None:
        """Return the points lost by the move of a node (KaTrain's GameNode.points_lost), or None."""
        move = node.move
        if move is None or node.parent is None:
            return None
        return points_lost(self.analysis(node.parent), self.analysis(node), move.player)


def load_saved_analyses(game: GameAnalysis) -> None:
    """Use the analysis data (KT) already saved in the nodes, as KaTrain's GameNode.load_analysis.

    A node whose data cannot be read is analyzed again, as in KaTrain.
    """
    version = game.root.get_property("KTV", "1.0")
    size_x, size_y = game.root.board_size
    for node in game.nodes:
        values = node.get_list_property("KT", [])
        if not values:
            continue
        try:
            main = decode_kt(values, version)
            ownership, policy = decode_kt_numbers(values, size_x * size_y)
        except ValueError:
            continue
        game.analyses[id(node)] = {**main, "policy": policy, "ownership": ownership}


def first_nodes(game: GameAnalysis) -> list[GoNode]:
    """Return the nodes that the first step analyzes: those without saved analysis data."""
    return [node for node in game.nodes if game.analysis(node) is None]


def reanalysis_nodes(game: GameAnalysis, mistakes_over: float | None, move_range: tuple[int, int] | None) -> list:
    """Return the nodes that "Re-analyze game" analyzes (KaTrain's Game.analyze_extra, mode "game").

    Args:
        game: The game.
        mistakes_over: Only nodes where the move or a move after it lost more than this, or None for all.
        move_range: Only nodes whose depth - 1 is in this range of move numbers (both ends included), or None.
    """
    chosen = []
    for node in game.nodes:
        losses = [game.points_lost(item) or 0 for item in [node, *node.children]]
        if mistakes_over is not None and max(losses) <= mistakes_over:
            continue
        if move_range and node.depth - 1 not in range(min(move_range), max(move_range) + 1):
            continue
        chosen.append(node)
    return chosen


def reanalysis_visits(game: GameAnalysis, max_visits: int) -> int:
    """Return KaTrain's visits of "Re-analyze game": the fewest visits asked for a node, plus max_visits."""
    return min((game.visits.get(id(node), 0) for node in game.nodes), default=0) + max_visits


def analyze_nodes(
    engine: Engine,
    game: GameAnalysis,
    nodes: Sequence[GoNode],
    settings: QuerySettings,
    progress: Callable[[int, int], None],
) -> None:
    """Analyze nodes with KataGo and put the answers into their analyses, the node before its children.

    The queries are sent together (KataGo answers them in the order of their priority and as it can);
    this function returns when all answers have come.
    """
    queries = [(node, query) for node in nodes if (query := node_query(node, settings)) is not None]
    answers = _ask_all(engine, [query for _, query in queries], progress)
    for (node, _), answer in zip(queries, answers, strict=True):
        game.visits[id(node)] = max(game.visits.get(id(node), 0), settings.visits)
        if "error" in answer or "rootInfo" not in answer:
            game.failed += 1
            continue
        _apply(game, node, answer)


def _apply(game: GameAnalysis, node: GoNode, answer: dict) -> None:
    """Put one answer into the analysis of its node and of the node before it."""
    analysis = game.analyses.setdefault(id(node), empty_analysis())
    parent = node.parent
    parent_analysis = game.analyses.setdefault(id(parent), empty_analysis()) if parent is not None else None
    move = node.move
    apply_answer(analysis, answer, parent_analysis, move.gtp() if move is not None else None)


def _ask_all(engine: Engine, queries: list[dict], progress: Callable[[int, int], None]) -> list[dict]:
    """Send all queries and wait for their final answers (KataGo calls back in its own thread)."""
    answers: list[dict | None] = [None] * len(queries)
    lock = threading.Lock()
    done = threading.Event()
    received = [0]

    def receiver(index: int) -> Callable[[dict], None]:
        def receive(answer: dict) -> None:
            if answer.get("isDuringSearch"):
                return
            with lock:
                answers[index] = answer
                received[0] += 1
                count = received[0]
            progress(count, len(queries))
            if count == len(queries):
                done.set()

        return receive

    if not queries:
        return []
    for index, query in enumerate(queries):
        engine.query(query, receiver(index))
    done.wait()
    return [answer or {"error": "no answer"} for answer in answers]


def analyze_game(
    engine: Engine, root: GoNode, settings: AnalysisSettings, values: EngineValues, progress: Progress
) -> GameAnalysis:
    """Analyze a game as KaTrain: the saved data, the first step, and "Re-analyze game" when it is on.

    Args:
        engine: KataGo.
        root: The root node of the game.
        settings: The settings of the analysis.
        values: The engine settings that the analysis uses.
        progress: Called after each answer, in KataGo's thread.

    Returns:
        The analyses of the nodes.
    """
    game = GameAnalysis(root)
    load_saved_analyses(game)
    visits = settings.fast_visits if settings.fast else values.max_visits
    first = QuerySettings(visits, values.wide_root_noise, settings.max_time, GAME_PRIORITY)
    analyze_nodes(engine, game, first_nodes(game), first, lambda done, total: progress(FIRST_STEP, done, total))
    if settings.reanalyze:
        again = QuerySettings(
            settings.reanalyze_visits or reanalysis_visits(game, values.max_visits),
            values.wide_root_noise,
            None,
            REANALYSIS_PRIORITY,
        )
        nodes = reanalysis_nodes(game, _mistakes_over(settings), _move_range(settings))
        analyze_nodes(engine, game, nodes, again, lambda done, total: progress(REANALYSIS_STEP, done, total))
    return game


def _mistakes_over(settings: AnalysisSettings) -> float | None:
    """Return the loss above which a move is analyzed again, or None to analyze every move again."""
    return settings.mistake_threshold() if settings.mistakes_only else None


def _move_range(settings: AnalysisSettings) -> tuple[int, int] | None:
    """Return the range of moves analyzed again, or None for the whole game."""
    if not settings.move_from and not settings.move_to:
        return None
    return settings.move_from, settings.move_to or END_OF_GAME
