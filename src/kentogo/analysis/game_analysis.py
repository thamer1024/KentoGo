"""The analyses of all nodes of a game, and how KataGo is asked about the nodes.

The analysis of a node is kept as KaTrain keeps it (see analysis.node_analysis), so the analysis data
(KT) can be read by KaTrain too. Saved analysis data is used as it is, as KaTrain's GameNode.load_analysis.
KataGo's reports during the search are not asked for, and the answers are put into the analyses in the
order of the tree, the node before its children, whatever order KataGo answers in, so the result is the
same every time. The steps of the analysis of a game are in analysis.analyze.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pysgf import GoNode

from kentogo.analysis.node_analysis import apply_answer, empty_analysis, points_lost
from kentogo.analysis.query import QuerySettings, node_query
from kentogo.record.katrain_kt import decode_kt, decode_kt_numbers

GAME_PRIORITY = -100  # KaTrain's PRIORITY_GAME_ANALYSIS.
REANALYSIS_PRIORITY = -1_000_000  # KaTrain's priority of "Re-analyze game".
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
        failed_nodes: The nodes that KataGo could not analyze (after the retries).
        loaded: The nodes whose analysis comes from saved analysis data (by id(node)).
        deep_nodes: The nodes whose moves were read deeply and can become problems (see analysis.analyze);
            KentoGo's own data (KGD) is written for them.
        deep_visits: The visits of the deep reading.
    """

    root: GoNode
    analyses: dict[int, dict] = field(default_factory=dict)
    visits: dict[int, int] = field(default_factory=dict)
    failed_nodes: list[GoNode] = field(default_factory=list)
    loaded: set[int] = field(default_factory=set)
    deep_nodes: list[GoNode] = field(default_factory=list)
    deep_visits: int = 0

    @property
    def failed(self) -> int:
        """Return the number of nodes that KataGo could not analyze."""
        return len(self.failed_nodes)

    @property
    def nodes(self) -> list[GoNode]:
        """Return all nodes of the tree, the node before its children (KaTrain's nodes_in_tree)."""
        return self.root.nodes_in_tree

    def analysis(self, node: GoNode) -> dict | None:
        """Return the analysis of a node, or None when it has none."""
        analysis = self.analyses.get(id(node))
        return analysis if analysis is not None and analysis["root"] is not None else None

    def points_lost(self, node: GoNode) -> float | None:
        """Return the score before a node's move minus the score after it (KaTrain's GameNode.points_lost), or None.

        Only used when the played move was not read in the position before it (see analysis.played_moves).
        """
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
        game.loaded.add(id(node))


def first_nodes(game: GameAnalysis) -> list[GoNode]:
    """Return the nodes that the first step analyzes: those without saved analysis data."""
    return [node for node in game.nodes if game.analysis(node) is None]


@dataclass(frozen=True)
class NodeStep:
    """How the nodes of one step are asked and how the answers are kept.

    Attributes:
        query: The query for a node (None when the node is not analyzed). It is called when the query is sent.
        apply: Puts KataGo's final answer for a node into the analyses.
    """

    query: Callable[[GoNode], dict | None]
    apply: Callable[[GameAnalysis, GoNode, dict], None]


def analysis_step(game: GameAnalysis, settings: QuerySettings) -> NodeStep:
    """Return the step that analyzes nodes (KaTrain's GameNode.analyze); each answer is kept in its own node."""

    def query(node: GoNode) -> dict | None:
        game.visits[id(node)] = max(game.visits.get(id(node), 0), settings.visits)  # Counted when asked.
        return node_query(node, settings)

    def keep(game: GameAnalysis, node: GoNode, answer: dict) -> None:
        apply_answer(game.analyses.setdefault(id(node), empty_analysis()), answer)

    return NodeStep(query, keep)


def analyze_nodes(
    engine: Engine, game: GameAnalysis, nodes: Sequence[GoNode], step: NodeStep, progress: Callable[[int, int], None]
) -> list[GoNode]:
    """Ask KataGo about nodes and keep the answers, the node before its children.

    The queries are sent together (KataGo answers them in the order of their priority and as it can);
    this function returns when all answers have come.

    Returns:
        The nodes that KataGo could not analyze.
    """
    queries = [(node, query) for node in nodes if (query := step.query(node)) is not None]
    answers = _ask_all(engine, [query for _, query in queries], progress)
    failed = []
    for (node, _), answer in zip(queries, answers, strict=True):
        if "error" in answer or "rootInfo" not in answer:
            failed.append(node)
            continue
        step.apply(game, node, answer)
    return failed


def analyze_with_retries(
    engine: Engine,
    game: GameAnalysis,
    nodes: Sequence[GoNode],
    step: NodeStep,
    progress: Callable[[int, int], None],
    retries: int,
) -> None:
    """Analyze nodes, ask again up to retries times for the nodes that failed, and keep the ones that still fail."""
    failed = analyze_nodes(engine, game, nodes, step, progress)
    for _ in range(retries):
        if not failed:
            break
        failed = analyze_nodes(engine, game, failed, step, progress)
    game.failed_nodes.extend(node for node in failed if node not in game.failed_nodes)


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
