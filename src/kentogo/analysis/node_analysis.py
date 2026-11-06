"""KaTrain's analysis of one node, kept as KaTrain keeps it, and how KataGo's answers go into it.

KaTrain keeps the analysis of a node as a dict (KaTrain 1.20.0, katrain/core/game_node.py,
GameNode.clear_analysis): "moves" (the candidate moves by GTP point, from KataGo's moveInfos),
"root" (KataGo's rootInfo), "ownership", "policy" and "completed". This module is written for
KentoGo with the same behavior as KaTrain's GameNode.update_move_analysis and the normal
(not refined, not limited to a region) part of GameNode.set_analysis. They are methods of
KaTrain's GameNode class, so they cannot be copied unchanged.

As in KaTrain, the answer for a node also updates the node before it: the move that was played
gets the score of the position after it (KataGo's rootInfo, with the move and the sequence after
it as "pv"), and the same rootInfo dict becomes the node's own "root".
"""

from __future__ import annotations

ADDITIONAL_MOVE_ORDER = 999  # KaTrain's order of a move that KataGo did not rank in this answer.
_SIGNS = {"B": 1, "W": -1}


def empty_analysis() -> dict:
    """Return the analysis of a node that is not analyzed yet (KaTrain's GameNode.clear_analysis)."""
    return {"moves": {}, "root": None, "ownership": None, "policy": None, "completed": False}


def update_move_analysis(analysis: dict, move_analysis: dict, move_gtp: str) -> None:
    """Put the analysis of one candidate move into a node's analysis (KaTrain's GameNode.update_move_analysis).

    A new move gets KaTrain's default "move" and "order"; a known one keeps the smaller order, and
    takes all the new values only when they come from more visits (otherwise only the missing ones).
    """
    current = analysis["moves"].get(move_gtp)
    if current is None:
        analysis["moves"][move_gtp] = {"move": move_gtp, "order": ADDITIONAL_MOVE_ORDER, **move_analysis}
        return
    current["order"] = min(current["order"], move_analysis.get("order", ADDITIONAL_MOVE_ORDER))
    if current["visits"] < move_analysis["visits"]:
        current.update(move_analysis)
    else:
        current.update({key: value for key, value in move_analysis.items() if key not in current})


def apply_answer(analysis: dict, answer: dict, parent_analysis: dict | None, move_gtp: str | None) -> None:
    """Put KataGo's final answer for a node into its analysis, as KaTrain's GameNode.set_analysis.

    The moves already known go to the end (KaTrain's ADDITIONAL_MOVE_ORDER) and the new ranking counts;
    then the node before it gets the score of the played move (see the module's docstring).

    Args:
        analysis: The node's analysis (changed).
        answer: KataGo's final answer (with "rootInfo" and "moveInfos").
        parent_analysis: The analysis of the node before it (changed), or None for the first node.
        move_gtp: The move of the node (GTP), or None for a node without a move.
    """
    for move_dict in analysis["moves"].values():
        move_dict["order"] = ADDITIONAL_MOVE_ORDER
    for move_analysis in answer["moveInfos"]:
        update_move_analysis(analysis, move_analysis, move_analysis["move"])
    analysis["ownership"] = answer.get("ownership")
    analysis["policy"] = answer.get("policy")
    analysis["root"] = answer["rootInfo"]
    if parent_analysis is not None and move_gtp is not None:
        answer["rootInfo"]["pv"] = [move_gtp] + (answer["moveInfos"][0]["pv"] if answer["moveInfos"] else [])
        update_move_analysis(parent_analysis, answer["rootInfo"], move_gtp)
    analysis["completed"] = True


def points_lost(before: dict | None, after: dict | None, color: str) -> float | None:
    """Return the points lost by a move (KaTrain's GameNode.points_lost), or None without both analyses."""
    if not before or not after or before.get("root") is None or after.get("root") is None:
        return None
    return _SIGNS[color] * (before["root"].get("scoreLead") - after["root"].get("scoreLead"))
