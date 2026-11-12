"""Write the analysis of a game into its SGF nodes, in KentoGo's own form: only what the problems need.

KentoGo writes no comments and no marks: the problems, the screens and the AI commentary read the analysis
data only. For each node:

- The comment keeps the user's notes (and the AI commentary) and KaTrain's own text (marked with
  KaTrain's invisible marker). What older versions of KentoGo wrote is removed: KentoGo's part (see
  record.kentogo_comment), and the text in KaTrain's form (see analysis.game_analysis.written_by_old_kentogo).
  In a game that KentoGo analyzed before (KGM), the marks of the best moves (MA and SQ) are removed too,
  as older versions of KentoGo wrote them.
- A move that KaTrain took back in a teaching game (KaTrain's text says so, or the analysis data that
  KentoGo saved before) gets "taken_back" in its analysis data, so that it is known without KaTrain's
  text (see mistakes.extract).
- The analysis data is written in KentoGo's own property (KGA, see record.kentogo_analysis) when the
  node's analysis is complete; KentoGo always writes it. KaTrain's KT is not written: its property and
  format are KaTrain's. KaTrain's own KT (of a game that KaTrain analyzed) is left as it is; the KT that an
  older KentoGo wrote (see analysis.game_analysis.written_by_old_kentogo) is removed, with the root's KTV.
  Only what the problems need is kept (KataGo answers with about twenty values for each candidate, the
  areas and the policy, which would make the file very large): the position's score, win rate and visits,
  KataGo's best move with its sequence and the moves played there (KEPT_MOVE_KEYS, the numbers rounded).
  The positions that can become problems (the moves that lost enough, see GameAnalysis.problem_nodes, and
  the positions before them) also keep the candidates that KataGo read with at least KEPT_SHARE of the
  visits, so that an answer is judged from the file. A move that can become a problem keeps its first
  instinct ("instinct"): its rank and probability in KataGo's policy, and the policy's first move (for
  the AI commentary), taken from the policy of the position before it, which is not kept itself.
- The KGD property that older versions of KentoGo wrote (KentoGo's own readings of the moves read deeply,
  which no feature uses) is removed from every node.
- The root gets CA, AP (KentoGo's version) and KGM[KentoGo], so that KentoGo knows that the losses are
  read in the position before each move (see analysis.played_moves).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pysgf import GoNode

from kentogo.analysis.game_analysis import GameAnalysis
from kentogo.analysis.played_moves import MODE_MARK
from kentogo.analysis.policy_ranking import policy_ranking
from kentogo.common.types import Move
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR, read_comment
from kentogo.record.kentogo_analysis import KGA_PROPERTY, encode_kga
from kentogo.record.kentogo_comment import split_kentogo_comment

PROGRAM_NAME = "KentoGo"
KEPT_ROOT_KEYS = ("scoreLead", "winrate", "visits")  # What is kept of a position.
KEPT_MOVE_KEYS = ("move", "order", "visits", "winrate", "scoreLead")  # What is kept of a candidate (and "pv").
OLD_MARKS = ("MA", "SQ")  # The marks of the best moves that older versions of KentoGo wrote.
OLD_DATA = "KGD"  # KentoGo's own readings that older versions of KentoGo wrote.
DIGITS = {"scoreLead": 2, "winrate": 4}  # The numbers are kept rounded to these digits.
KEPT_SHARE = 0.01  # A candidate of a problem position is kept when KataGo read it with this share of the visits.


@dataclass(frozen=True)
class WriteSettings:
    """What the writing needs besides the analysis.

    Attributes:
        version: KentoGo's version, for AP.
    """

    version: str


def write_analysis(game: GameAnalysis, write: WriteSettings) -> None:
    """Write the analysis into the properties of all nodes of the game (the nodes are changed)."""
    analyzed_before = game.root.get_property("KGM") == MODE_MARK
    problems = {id(node) for node in game.problem_nodes}
    with_candidates = problems | {id(node.parent) for node in game.problem_nodes}
    for node in game.nodes:
        node.properties.pop(OLD_DATA, None)
        marks = {}
        if node.parent is None:
            _write_root(game, node, write)
        elif _clean_node(game, node):
            marks["taken_back"] = True
        if analyzed_before:
            _remove_old_marks(node)
        if id(node) in problems:
            marks |= _instinct(game, node)
        keep = kept_problem_analysis if id(node) in with_candidates else kept_analysis
        _write_kga(game, node, keep, marks)


def _clean_node(game: GameAnalysis, node: GoNode) -> bool:
    """Remove what older versions of KentoGo wrote into a node's comment (see the module's docstring).

    Returns:
        True if KaTrain took the node's move back in a teaching game.
    """
    parts = _comment_parts(node, game.old_kentogo_kt)
    _, info = read_comment(SEPARATOR.join(parts.katrain))
    _set_comments(node, parts)
    return (info is not None and info.teaching_undo) or bool((game.analysis(node) or {}).get("taken_back"))


def _remove_old_marks(node: GoNode) -> None:
    """Remove the marks of the best moves (MA and SQ) of a game that KentoGo analyzed before (KGM)."""
    for key in OLD_MARKS:
        node.properties.pop(key, None)


def _write_kga(game: GameAnalysis, node: GoNode, keep: Callable[[dict, set[str]], dict], marks: dict) -> None:
    """Write KentoGo's analysis data of a node when its analysis is complete, and remove old data.

    KaTrain's KT stays; only the KT that an older KentoGo wrote is removed.

    Args:
        keep: What is kept of the analysis (kept_analysis, or kept_problem_analysis for a problem position).
        marks: What is kept of the move besides: "taken_back" (KaTrain took it back in a teaching game) and
            "instinct" (see _instinct).
    """
    node.properties.pop(KGA_PROPERTY, None)
    if game.old_kentogo_kt:
        node.properties.pop("KT", None)
    analysis = game.analysis(node)
    if analysis is not None and analysis.get("completed"):
        node.properties[KGA_PROPERTY] = encode_kga({**keep(analysis, _played_moves(node)), **marks})


def kept_analysis(analysis: dict, played: set[str]) -> dict:
    """Return what a position that cannot become a problem keeps (a copy): its values, the best move and the moves
    played there (see the module's docstring).

    Args:
        analysis: The analysis (not changed).
        played: The moves played in the position (the moves of the node's children).
    """
    return _kept(analysis, {point for point, values in analysis["moves"].items() if values.get("order") == 0} | played)


def kept_problem_analysis(analysis: dict, played: set[str]) -> dict:
    """Return what a position that can become a problem keeps (a copy): as kept_analysis, and the candidates
    that KataGo read with at least KEPT_SHARE of the visits."""
    visits = analysis["root"].get("visits", 0)
    read = {point for point, values in analysis["moves"].items() if values.get("visits", 0) >= KEPT_SHARE * visits}
    return _kept(analysis, read | set(kept_analysis(analysis, played)["moves"]))


def _kept(analysis: dict, wanted: set[str]) -> dict:
    """Return the kept values of an analysis with the wanted candidates, in KataGo's order of the analysis."""
    moves = {point: _kept_move(values) for point, values in analysis["moves"].items() if point in wanted}
    return {"root": _rounded(analysis["root"], KEPT_ROOT_KEYS), "moves": moves, "completed": True}


def _kept_move(values: dict) -> dict:
    """Return the kept values of a candidate: KEPT_MOVE_KEYS, and the sequence of KataGo's best move."""
    kept = _rounded(values, KEPT_MOVE_KEYS)
    if values.get("order") == 0 and values.get("pv"):
        kept["pv"] = list(values["pv"])
    return kept


def _rounded(values: dict, keys: tuple[str, ...]) -> dict:
    """Return the values of the keys (those that are there), the numbers of DIGITS rounded."""
    kept = {key: values[key] for key in keys if key in values}
    for key, digits in DIGITS.items():
        if isinstance(kept.get(key), float):
            kept[key] = round(kept[key], digits)
    return kept


def _instinct(game: GameAnalysis, node: GoNode) -> dict:
    """Return the first instinct of a move that can become a problem: {"instinct": {...}}, or {} when unknown.

    It is the move's rank (from 1) and probability in KataGo's policy of the position before it, and the
    policy's first move and its probability. Without that policy (a position read before and not again), the
    instinct kept before is used.
    """
    move = node.move
    ranking = policy_ranking(game.analysis(node.parent) or {}, move.player, node.board_size)
    if not ranking:
        saved = (game.analysis(node) or {}).get("instinct")
        return {"instinct": saved} if saved else {}
    played = Move(move.player, move.coords)
    rank, probability = next(
        ((number, value) for number, (value, ranked) in enumerate(ranking, start=1) if ranked == played), (0, 0.0)
    )
    best_value, best = ranking[0]
    return {
        "instinct": {
            "rank": rank,
            "probability": round(probability, 4),
            "best": best.gtp(),
            "best_probability": round(best_value, 4),
        }
    }


def _played_moves(node: GoNode) -> set[str]:
    """Return the moves played in a position (GTP points of the moves of its children)."""
    return {child.move.gtp() for child in node.children if child.move is not None}


def _write_root(game: GameAnalysis, root: GoNode, write: WriteSettings) -> None:
    """Write the root's CA, AP and KGM, and remove what older versions of KentoGo wrote (KentoGo's part of the
    comment, and the KTV of an older KentoGo's KT)."""
    root.properties["CA"] = ["UTF-8"]
    root.properties["AP"] = [f"{PROGRAM_NAME}:{write.version}"]
    root.properties["KGM"] = [MODE_MARK]
    if game.old_kentogo_kt:
        root.properties.pop("KTV", None)
    _set_comments(root, _comment_parts(root, game.old_kentogo_kt))


@dataclass(frozen=True)
class CommentParts:
    """The parts of a node's comment that stay when KentoGo writes the game again.

    Attributes:
        notes: The user's notes (and the AI commentary): the parts without KaTrain's marker.
        katrain: KaTrain's own parts, as they are (with KaTrain's marker).
    """

    notes: str
    katrain: tuple[str, ...]


def _comment_parts(node: GoNode, old_kentogo: bool) -> CommentParts:
    """Return the parts of a node's comment without KentoGo's part (and without an older KentoGo's text in KaTrain's form)."""
    rest = split_kentogo_comment("".join(node.get_list_property("C", []))).rest
    notes, katrain = [], []
    for part in rest.split(SEPARATOR):
        if INTERNAL_MARKER not in part:
            notes.append(part)
        elif not old_kentogo:
            katrain.append(part)
    return CommentParts("".join(notes).strip(), tuple(katrain))


def _set_comments(node: GoNode, parts: CommentParts) -> None:
    """Write the notes and KaTrain's parts into C, joined with the separator (or remove C)."""
    comments = [f"{parts.notes}\n"] if parts.notes else []
    comments += parts.katrain
    if comments:
        node.properties["C"] = [SEPARATOR.join(comments).strip("\n")]
    else:
        node.properties.pop("C", None)
