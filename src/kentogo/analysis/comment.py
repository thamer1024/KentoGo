"""The comment that KaTrain writes on an analyzed move of an SGF file, written by KentoGo.

The text is the same as KaTrain's GameNode.comment(sgf=True, interactive=False) (KaTrain 1.20.0,
katrain/core/game_node.py), in KaTrain's language: the move, the score and the win rate after it,
the points lost and KaTrain's top move (or "best move"), the top move's sequence, the rank of the
move in KataGo's policy and the top policy move, and the lines of a move taken back in a teaching game.
KaTrain's method is part of its GameNode class (it uses the tree, i18n and Kivy themes), so it cannot
be copied unchanged; this module is written for KentoGo with the same behavior, from the same pieces:
GameNode.candidate_moves, points_lost, format_score, format_winrate, move_policy_stats, policy_ranking
and make_pv. KaTrain's own standalone helper var_to_grid is used unchanged (vendor.katrain_analysis).

Two parts of KaTrain's comment are left out because KentoGo's analysis never has them: the AI's
thoughts (only for moves that KaTrain's AI played in that session) and the "SGF Comments" part
(KaTrain keeps a loaded comment as a note instead). The analyses are KaTrain's analysis dicts:
"root" (rootInfo of KataGo), "moves" (moveInfos by GTP point) and "policy".
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.common.types import Move, opponent
from kentogo.record.katrain_texts import KATRAIN_TEXTS
from kentogo.vendor.katrain_analysis import var_to_grid

DEFAULT_LANGUAGE = "en"  # KaTrain's texts when a language has none.
_SIGNS = {"B": 1, "W": -1}  # KaTrain's GameNode.player_sign.


@dataclass(frozen=True)
class CommentedMove:
    """The move that gets a comment.

    Attributes:
        number: Its move number (KaTrain's node depth).
        move: The move.
        auto_undo: KaTrain took it back in a teaching game (KaTrain writes two more lines).
        points_lost: The loss to write (see analysis.played_moves), or None for the score before minus the score after.
    """

    number: int
    move: Move
    auto_undo: bool = False
    points_lost: float | None = None


def move_comment(
    commented: CommentedMove,
    before: dict,
    after: dict,
    size: tuple[int, int],
    language: str,
) -> str:
    """Return KaTrain's comment on a move (as GameNode.comment(sgf=True, interactive=False)).

    Args:
        commented: The move.
        before: The analysis of the position before the move (KaTrain's parent node).
        after: The analysis of the position after the move (KaTrain's node of the move).
        size: The board size (x, y).
        language: KaTrain's language code, such as "jp".

    Returns:
        The comment, each line ending with a newline.
    """
    texts = KATRAIN_TEXTS.get(language, KATRAIN_TEXTS[DEFAULT_LANGUAGE])
    move = commented.move
    text = texts["move"].format(number=commented.number) + f": {move.color} {move.gtp()}\n"
    text += texts["Info:score"].format(score=format_score(_score(after), _score(after), texts)) + "\n"
    text += texts["Info:winrate"].format(winrate=format_winrate(_winrate(after), texts)) + "\n"
    text += _top_move_lines(commented, before, after, size, texts)
    text += _policy_lines(move, before, size, texts)
    if commented.auto_undo:
        text += _undo_lines(move, after, size, texts)
    return text


def _top_move_lines(
    commented: CommentedMove,
    before: dict,
    after: dict,
    size: tuple[int, int],
    texts: dict[str, str],
) -> str:
    """Return the lines about the points lost, KaTrain's top move and its sequence."""
    move = commented.move
    top = top_candidate(before, move.color, size)
    if top["move"] != move.gtp():
        text = ""
        points_lost = commented.points_lost
        if points_lost is None:
            points_lost = _SIGNS[move.color] * (_score(before) - _score(after))
        if points_lost > 0.5:
            text += texts["Info:point loss"].format(points_lost=points_lost) + "\n"
        score = format_score(top["scoreLead"], _score(after), texts)
        text += texts["Info:top move"].format(top_move=top["move"], score=score) + "\n"
    else:
        text = texts["Info:best move"] + "\n"
    if top.get("pv"):
        text += texts["Info:PV"].format(pv=f"{move.color}{' '.join(top['pv'])}") + "\n"
    return text


def _policy_lines(move: Move, before: dict, size: tuple[int, int], texts: dict[str, str]) -> str:
    """Return the lines about the rank of the move in the policy and the top policy move."""
    ranking = policy_ranking(before, move.color, size)
    rank, probability = next(
        ((index + 1, value) for index, (value, ranked) in enumerate(ranking) if ranked == move), (None, 0.0)
    )
    text = ""
    if rank is not None:
        text += texts["Info:policy rank"].format(rank=rank, probability=probability) + "\n"
    if rank != 1 and ranking:
        best_value, best_move = ranking[0]
        text += texts["Info:policy best"].format(move=best_move.gtp(), probability=best_value) + "\n"
    return text


def _undo_lines(move: Move, after: dict, size: tuple[int, int], texts: dict[str, str]) -> str:
    """Return the lines of a move taken back in a teaching game, with the predicted sequence after it."""
    text = texts["Info:teaching undo"] + "\n"
    next_color = opponent(move.color)
    top_pv = after.get("root") is not None and top_candidate(after, next_color, size).get("pv")
    if top_pv:
        text += texts["Info:undo predicted PV"].format(pv=f"{next_color}{' '.join(top_pv)}") + "\n"
    return text


def top_candidate(analysis: dict, next_color: str, size: tuple[int, int]) -> dict:
    """Return KaTrain's top candidate move of a position (the first of GameNode.candidate_moves)."""
    return candidate_moves(analysis, next_color, size)[0]


def candidate_moves(analysis: dict, next_color: str, size: tuple[int, int]) -> list[dict]:
    """Return KaTrain's candidate moves of a position, as GameNode.candidate_moves.

    The candidates are sorted by KataGo's order and then by the points lost, and each gets its
    "pointsLost" (and KaTrain's "relativePointsLost" and "winrateLost"); without candidate moves,
    the move with the highest policy (or a pass) is the only candidate, as in KaTrain.
    """
    root = analysis["root"]
    moves = list((analysis.get("moves") or {}).values())
    if not moves:
        ranking = policy_ranking(analysis, next_color, size)
        point = ranking[0][1].gtp() if ranking else "pass"
        return [{**root, "pointsLost": 0, "winrateLost": 0, "order": 0, "move": point, "pv": [point]}]
    sign = _SIGNS[next_color]
    top = [values for values in moves if values["order"] == 0]
    top_score = top[0]["scoreLead"] if top else root["scoreLead"]
    candidates = [
        {
            "pointsLost": sign * (root["scoreLead"] - values["scoreLead"]),
            "relativePointsLost": sign * (top_score - values["scoreLead"]),
            "winrateLost": sign * (root["winrate"] - values["winrate"]),
            **values,
        }
        for values in moves
    ]
    return sorted(candidates, key=lambda values: (values["order"], values["pointsLost"]))


def policy_ranking(analysis: dict, next_color: str, size: tuple[int, int]) -> list[tuple[float, Move]]:
    """Return the moves from the highest policy value to the lowest, as KaTrain's GameNode.policy_ranking.

    The points are taken column by column from the left (each from the bottom), and the pass last;
    the sort keeps that order for equal values, as in KaTrain. Without a policy, the list is empty.
    """
    policy = analysis.get("policy")
    if not policy:
        return []
    columns, rows = size
    grid = var_to_grid(policy, size=(columns, rows))
    moves = [(grid[y][x], Move(next_color, (x, y))) for x in range(columns) for y in range(rows)]
    moves.append((policy[-1], Move(next_color, None)))
    return sorted(moves, key=lambda value_move: -value_move[0])


def format_score(score: float | None, own_score: float | None, texts: dict[str, str]) -> str | None:
    """Return a score as KaTrain's GameNode.format_score, such as "B+2.5".

    Args:
        score: The score lead (black's side).
        own_score: The score of the node that formats it, used when score is None. (KaTrain uses it
            for a score of 0 too, "score or self.score"; KentoGo writes 0 as 0.)
        texts: KaTrain's texts of the language.

    Returns:
        The text, or None when there is no score.
    """
    return _score_text(own_score if score is None else score, texts)


def _score_text(score: float | None, texts: dict[str, str]) -> str | None:
    """Return a score lead as KaTrain writes it (the leading player and the points), or None without one."""
    if score is None:
        return None
    leading = "B" if score >= 0 else "W"
    return f"{texts[f'short color {leading}']}+{abs(score):.1f}"


def format_winrate(winrate: float | None, texts: dict[str, str]) -> str | None:
    """Return a win rate as KaTrain's GameNode.format_winrate, such as "B 61.2%", or None without one."""
    if winrate is None:
        return None
    leading = "B" if winrate > 0.5 else "W"
    return f"{texts[f'short color {leading}']} {max(winrate, 1 - winrate):.1%}"


def _score(analysis: dict) -> float | None:
    """Return the score lead of an analysis (KaTrain's GameNode.score)."""
    return (analysis.get("root") or {}).get("scoreLead")


def _winrate(analysis: dict) -> float | None:
    """Return the win rate of an analysis (KaTrain's GameNode.winrate)."""
    return (analysis.get("root") or {}).get("winrate")
