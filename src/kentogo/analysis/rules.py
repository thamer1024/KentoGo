"""The two modes of the analysis: KaTrain's own rules, and KentoGo's rules that fix some of KaTrain's problems.

The mode is chosen by the setting katrain_compatible (see analysis_settings). Each mode is a set of
small functions, so that the analysis itself does not need to know which mode it runs in.

KaTrain compatible (KaTrain 1.20.0, katrain/core/game.py and game_node.py), as KaTrain does it:
- "Re-analyze game" uses the fewest visits asked for any node, plus max_visits. Nodes read from
  saved analysis data count as 0 visits, so a saved game is not analyzed more deeply.
- Only the mistakes: a node where its move or a move after it lost more than the fourth threshold
  from the end of eval_thresholds.
- A range of moves: the nodes whose depth - 1 is in the range (moves 30 to 150 are the nodes of 31 to 151).
- A node that KataGo could not analyze is not asked again.
- A score of exactly 0 is shown as the score of the node itself ("score or self.score").
- With the marks on, the start message is written twice at the root.

KentoGo's mode:
- "Re-analyze game" counts the visits of the saved analysis data, so it always reads more deeply.
- Only the mistakes: a loss of reanalyze_threshold points or more (its own setting).
- A range of moves: the positions that the losses of those moves need (before the first move to
  after the last one), in whichever order the range is given.
- A node that KataGo could not analyze is asked again (retries times).
- A score of 0 is shown as 0, and the start message is written once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pysgf import GoNode

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.comment import ScoreFormat, format_score, format_score_exactly
from kentogo.analysis.game_analysis import GameAnalysis

END_OF_GAME = 100_000  # The end of the range of moves when move_to is 0.


@dataclass(frozen=True)
class AnalysisRules:
    """The rules of one mode.

    Attributes:
        reanalysis_visits: The visits of "Re-analyze game" (the game, max_visits).
        reanalysis_nodes: The nodes that "Re-analyze game" analyzes.
        retries: How many times a failed node is asked again.
        score_format: How a score is written in the comments.
        start_messages: The comments at the start of the root's comment, from the start message (or None).
    """

    reanalysis_visits: Callable[[GameAnalysis, int], int]
    reanalysis_nodes: Callable[[GameAnalysis, AnalysisSettings], list[GoNode]]
    retries: Callable[[AnalysisSettings], int]
    score_format: ScoreFormat
    start_messages: Callable[[str | None], list[str]]


def rules_for(settings: AnalysisSettings) -> AnalysisRules:
    """Return the rules of the mode chosen in the settings."""
    return KATRAIN_RULES if settings.katrain_compatible else KENTOGO_RULES


def katrain_reanalysis_visits(game: GameAnalysis, max_visits: int) -> int:
    """KaTrain: the fewest visits asked for any node (0 for saved analysis data), plus max_visits."""
    return min((game.visits.get(id(node), 0) for node in game.nodes), default=0) + max_visits


def kentogo_reanalysis_visits(game: GameAnalysis, max_visits: int) -> int:
    """KentoGo: the fewest visits of any node, counting the visits of saved analysis data, plus max_visits."""
    return min((_node_visits(game, node) for node in game.nodes), default=0) + max_visits


def _node_visits(game: GameAnalysis, node: GoNode) -> int:
    """Return the visits asked for a node, or the visits of its saved analysis data."""
    analysis = game.analysis(node)
    saved = analysis["root"].get("visits", 0) if analysis is not None else 0
    return max(game.visits.get(id(node), 0), saved)


def katrain_reanalysis_nodes(game: GameAnalysis, settings: AnalysisSettings) -> list[GoNode]:
    """KaTrain: the mistakes over the fourth threshold from the end, and the nodes whose depth - 1 is in the range."""
    threshold = settings.mistake_threshold()
    low, high = _range(settings)
    return [
        node
        for node in game.nodes
        if (not settings.mistakes_only or _largest_loss(game, node) > threshold) and low <= node.depth - 1 <= high
    ]


def kentogo_reanalysis_nodes(game: GameAnalysis, settings: AnalysisSettings) -> list[GoNode]:
    """KentoGo: the losses of reanalyze_threshold or more, and the positions that the moves of the range need."""
    low, high = _range(settings)
    return [
        node
        for node in game.nodes
        if (not settings.mistakes_only or _largest_loss(game, node) >= settings.reanalyze_threshold)
        and low - 1 <= node.depth <= high
    ]


def _largest_loss(game: GameAnalysis, node: GoNode) -> float:
    """Return the largest loss of the node's move and the moves after it (0 when not known), as KaTrain."""
    return max(game.points_lost(item) or 0 for item in [node, *node.children])


def _range(settings: AnalysisSettings) -> tuple[int, int]:
    """Return the range of moves analyzed again, the smaller first (the whole game when none is set)."""
    if not settings.move_from and not settings.move_to:
        return -1, END_OF_GAME
    ends = (settings.move_from, settings.move_to or END_OF_GAME)
    return min(ends), max(ends)


def katrain_start_messages(start: str | None) -> list[str]:
    """KaTrain: "comments += [*comments, ...]" puts the start message in twice."""
    return [start, start] if start else []


def kentogo_start_messages(start: str | None) -> list[str]:
    """KentoGo: the start message once."""
    return [start] if start else []


KATRAIN_RULES = AnalysisRules(
    katrain_reanalysis_visits, katrain_reanalysis_nodes, lambda _settings: 0, format_score, katrain_start_messages
)
KENTOGO_RULES = AnalysisRules(
    kentogo_reanalysis_visits,
    kentogo_reanalysis_nodes,
    lambda settings: settings.retries,
    format_score_exactly,
    kentogo_start_messages,
)
