"""Write the analysis of a game into its SGF nodes, in KentoGo's own form.

Which nodes get comments and marks follows KaTrain 1.20.0's GameNode.sgf_properties and
Game.write_sgf (katrain/core/game_node.py and game.py); the comments and the analysis data are
KentoGo's own. For each node:

- The user's notes stay at the top of the comment. KaTrain's own text (marked with KaTrain's
  invisible marker) stays as it is after them, but the text in KaTrain's form that an older KentoGo
  wrote (see analysis.game_analysis.written_by_old_kentogo) is removed. KentoGo's part (see
  record.kentogo_comment) is written again each time.
- KentoGo's comment (see analysis.kentogo_comment) is written when the node and the node before it are
  analyzed, and either the node has notes, or its player gets comments (save_comments_player)
  and the class of its loss is chosen in save_feedback (a loss of exactly 0 gets none, as in KaTrain).
  A move that KaTrain took back in a teaching game (KaTrain's text says so, or the analysis data
  that KentoGo saved before) gets "taken_back" in its analysis data, so that it is known without
  KaTrain's text (see mistakes.extract).
- The best moves are marked (MA for the top move, SQ for moves losing 0.5 points or less) when save_marks is on.
- The analysis data is written in KentoGo's own property (KGA, see record.kentogo_analysis) when the
  node's analysis is complete; KentoGo always writes it. KaTrain's KT is not written: its property and
  format are KaTrain's. KaTrain's own KT (of a game that KaTrain analyzed) is left as it is; the KT that an
  older KentoGo wrote (see analysis.game_analysis.written_by_old_kentogo) is removed, with the root's KTV.
  KataGo answers with about twenty values for each of some twenty candidate moves, and most of them are
  not used. So only the positions that can become problems (the deep nodes and the positions before
  them) keep everything, for features that come later. The other positions keep the values that KentoGo
  uses (KEPT_MOVE_KEYS), the candidates that KataGo read with at least KEPT_SHARE of the visits (and the
  best move and the moves played there), the sequences of the first KEPT_SEQUENCES candidates and the
  moves played, and the policy (for the comments when the game is analyzed again), but not the areas.
- KentoGo's own data (KGD, see record.kentogo_data) is written for the moves read deeply (the game's
  deep_nodes, see analysis.analyze), and removed from the other nodes, so that it always goes with
  this analysis. It has the analysis it was made from ("base": the score and the visits of the position
  before the move), KataGo's values of the played move and the best move there, the position after the
  played move ("played_after"), and KentoGo's own readings (see analysis.kentogo_reading), each under
  its name, with its areas as a Grid. The last node of the main line gets "end_of_game" (the last
  position read deeply, with its areas), as a move's data or, when it was not read deeply, as data
  of the kind "end".
- The root gets KentoGo's part of the comment (the version that analyzed the game), CA, AP and
  KGM[KentoGo], so that KentoGo knows that the losses are read in the position before each move
  (see analysis.played_moves).

Which players get comments: KaTrain uses the players set on its screen at that time; KentoGo uses the
player names in the game (a player that is not KaTrain's AI counts as a human).
"""

from __future__ import annotations

from dataclasses import dataclass

from pysgf import GoNode
from pysgf import Move as SgfMove

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.candidate_moves import candidate_moves
from kentogo.analysis.game_analysis import GameAnalysis
from kentogo.analysis.kentogo_comment import CommentedMove, comment_language, kentogo_move_comment, kentogo_root_comment
from kentogo.analysis.kentogo_reading import END_OF_GAME
from kentogo.analysis.played_moves import MODE_MARK, played_move_loss
from kentogo.common.types import Move
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR, read_comment
from kentogo.record.kentogo_analysis import KGA_PROPERTY, encode_kga
from kentogo.record.kentogo_comment import kentogo_part, split_kentogo_comment
from kentogo.record.kentogo_data import Grid, write_kgd
from kentogo.record.players import AI, classify_katrain_name
from kentogo.vendor.katrain_analysis import evaluation_class

PROGRAM_NAME = "KentoGo"
# What the positions that cannot become problems keep of each candidate move: the values that KentoGo uses
# (the same values as KaTrain uses in katrain/core/game_node.py, ai.py and gui).
KEPT_MOVE_KEYS = ("move", "order", "visits", "winrate", "scoreLead", "prior", "pv")
KEPT_SHARE = 0.01  # A candidate is kept when KataGo read it with at least this share of the visits.
KEPT_SEQUENCES = 5  # The sequences of the candidates of KataGo's order below this are kept.


@dataclass(frozen=True)
class WriteSettings:
    """What the comments need besides the settings of the analysis.

    Attributes:
        settings: The settings of the analysis.
        version: KentoGo's version, for the root's comment and AP.
    """

    settings: AnalysisSettings
    version: str


def write_analysis(game: GameAnalysis, write: WriteSettings) -> None:
    """Write the analysis into the properties of all nodes of the game (the nodes are changed)."""
    commented = _players_with_comments(game.root, write.settings)
    deep = {id(node) for node in game.deep_nodes}
    full = deep | {id(node.parent) for node in game.deep_nodes}
    for node in game.nodes:
        write_kgd(node, _kentogo_data(game, node, id(node) in deep))
        taken_back = False
        if node.parent is None:
            _write_root(game, node, write)
        else:
            taken_back = _write_node(game, node, commented, write)
        _write_kga(game, node, id(node) in full, taken_back)


def _write_node(game: GameAnalysis, node: GoNode, commented: dict[str, bool], write: WriteSettings) -> bool:
    """Write KentoGo's comment, the marks and the analysis data of one node.

    Returns:
        True if KaTrain took the move back in a teaching game.
    """
    parts = _comment_parts(node, game.old_kentogo_kt)
    _, info = read_comment(SEPARATOR.join(parts.katrain))
    saved = game.analysis(node) or {}
    taken_back = (info is not None and info.teaching_undo) or bool(saved.get("taken_back"))
    kentogo = ""
    if _gets_comment(game, node, parts.notes, commented, write):
        if write.settings.save_marks:
            _write_marks(game, node)
        kentogo = _comment(game, node, taken_back, write)
    _set_comments(node, parts, kentogo)
    return taken_back


def _gets_comment(
    game: GameAnalysis, node: GoNode, notes: str, commented: dict[str, bool], write: WriteSettings
) -> bool:
    """Tell whether KaTrain writes its comment on a node (see the module's docstring)."""
    move, settings = node.move, write.settings
    if move is None or game.analysis(node.parent) is None or game.analysis(node) is None:
        return False
    points_lost = played_move_loss(game, node)
    show_class = bool(points_lost) and settings.save_feedback[evaluation_class(points_lost, settings.eval_thresholds)]
    return bool(notes) or (commented.get(move.player, False) and show_class)


def _comment(game: GameAnalysis, node: GoNode, taken_back: bool, write: WriteSettings) -> str:
    """Return KentoGo's comment on the move of a node."""
    move = node.move
    commented = CommentedMove(node.depth, Move(move.player, move.coords), played_move_loss(game, node), taken_back)
    before, after = game.analysis(node.parent), game.analysis(node)
    language = comment_language(write.settings.language)
    return kentogo_move_comment(commented, before, after, node.board_size, language)


def _kentogo_data(game: GameAnalysis, node: GoNode, deep: bool) -> dict | None:
    """Return KentoGo's own data of a node (see record.kentogo_data), or None when it has none."""
    readings = game.readings.get(id(node), {})
    if not deep:
        if END_OF_GAME not in readings:
            return None
        return {"kind": "end", "visits": game.deep_visits, END_OF_GAME: _with_grids(readings[END_OF_GAME])}
    before = game.analysis(node.parent)
    played = before["moves"].get(node.move.gtp(), {})
    best = next((values for values in before["moves"].values() if values.get("order") == 0), {})
    root = before["root"]
    after = game.analysis(node)["root"]
    data = {
        "kind": "move",
        "visits": game.deep_visits,
        "base": {"scoreLead": root.get("scoreLead"), "visits": root.get("visits")},
        "played": _move_values(played),
        "best": _move_values(best),
        "played_after": {key: after[key] for key in ("scoreLead", "winrate", "visits") if key in after},
    }
    for name, values in readings.items():
        data[name] = _with_grids(values)
    return data


def _with_grids(value: object) -> object:
    """Return a reading with each "ownership" (KataGo's areas) as a Grid, so that it takes little room."""
    if isinstance(value, dict):
        return {key: Grid(tuple(item)) if key == "ownership" else _with_grids(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_with_grids(item) for item in value]
    return value


def _move_values(values: dict) -> dict:
    """Return KataGo's values of a candidate move that KentoGo keeps."""
    keys = ("move", "scoreLead", "winrate", "visits", "pv")
    return {key: values[key] for key in keys if key in values}


def _write_marks(game: GameAnalysis, node: GoNode) -> None:
    """Mark KataGo's top move (MA) and the moves losing 0.5 points or less (SQ) before the node, as KaTrain."""
    candidates = candidate_moves(game.analysis(node.parent), node.move.player, node.board_size)
    top = SgfMove.from_gtp(candidates[0]["move"]).sgf(node.board_size)
    good = [
        SgfMove.from_gtp(values["move"]).sgf(node.board_size)
        for values in candidates
        if values["pointsLost"] <= 0.5 and values["move"] != "pass" and values["order"] != 0
    ]
    if good and "SQ" not in node.properties:
        node.properties["SQ"] = good
    if top and "MA" not in node.properties:
        node.properties["MA"] = [top]


def _write_kga(game: GameAnalysis, node: GoNode, full: bool, taken_back: bool) -> None:
    """Write KentoGo's analysis data of a node when its analysis is complete, and remove old data.

    KaTrain's KT stays; only the KT that an older KentoGo wrote is removed.

    Args:
        full: Keep everything (a position that can become a problem), or only what is used (see the module's docstring).
        taken_back: KaTrain took the node's move back in a teaching game (kept as "taken_back").
    """
    node.properties.pop(KGA_PROPERTY, None)
    if game.old_kentogo_kt:
        node.properties.pop("KT", None)
    analysis = game.analysis(node)
    if analysis is not None and analysis.get("completed"):
        kept = analysis if full else {**kept_analysis(analysis, _played_moves(node)), "ownership": None}
        kept = {key: value for key, value in kept.items() if key != "taken_back"}
        node.properties[KGA_PROPERTY] = encode_kga({**kept, "taken_back": True} if taken_back else kept)


def kept_analysis(analysis: dict, played: set[str]) -> dict:
    """Return the analysis of a position that cannot become a problem, with only what is used (a copy).

    Args:
        analysis: The analysis (not changed).
        played: The moves played in the position (the moves of the node's children).
    """
    visits = analysis["root"].get("visits", 0)
    moves = {}
    for point, values in analysis["moves"].items():
        order = values.get("order")
        if not (order == 0 or point in played or values.get("visits", 0) >= KEPT_SHARE * visits):
            continue
        kept = {key: values[key] for key in KEPT_MOVE_KEYS if key in values}
        if order is not None and order >= KEPT_SEQUENCES and point not in played:
            kept.pop("pv", None)
        moves[point] = kept
    return {**analysis, "moves": moves}


def _played_moves(node: GoNode) -> set[str]:
    """Return the moves played in a position (GTP points of the moves of its children)."""
    return {child.move.gtp() for child in node.children if child.move is not None}


def _write_root(game: GameAnalysis, root: GoNode, write: WriteSettings) -> None:
    """Write the root's comment, CA, AP and KGM (and remove the KTV that an older KentoGo wrote)."""
    root.properties["CA"] = ["UTF-8"]
    root.properties["AP"] = [f"{PROGRAM_NAME}:{write.version}"]
    root.properties["KGM"] = [MODE_MARK]
    if game.old_kentogo_kt:
        root.properties.pop("KTV", None)
    language = comment_language(write.settings.language)
    _set_comments(root, _comment_parts(root, game.old_kentogo_kt), kentogo_root_comment(write.version, language))


@dataclass(frozen=True)
class CommentParts:
    """The parts of a node's comment that stay when KentoGo writes it again.

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


def _set_comments(node: GoNode, parts: CommentParts, kentogo: str) -> None:
    """Write the notes, KaTrain's parts and KentoGo's part into C, joined with the separator (or remove C)."""
    comments = [f"{parts.notes}\n"] if parts.notes else []
    comments += parts.katrain
    if kentogo:
        comments.append(f"\n{kentogo_part(kentogo)}")
    if comments:
        node.properties["C"] = [SEPARATOR.join(comments).strip("\n")]
    else:
        node.properties.pop("C", None)


def _players_with_comments(root: GoNode, settings: AnalysisSettings) -> dict[str, bool]:
    """Return which players get comments: all when eval_show_ai is on, otherwise the humans."""
    return {
        color: settings.eval_show_ai or classify_katrain_name(str(root.get_property("P" + color, ""))) != AI
        for color in "BW"
    }
