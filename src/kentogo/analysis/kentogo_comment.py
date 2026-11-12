"""KentoGo's own comment on an analyzed move (not KaTrain's text, which KentoGo only reads).

The comment tells, in Japanese or English (KENTOGO_TEXTS):

- the move number, the player and the move;
- the points lost (when more than LOSS_SHOWN) and the best move with the score and win rate after it,
  or that the move was the best;
- the score and win rate after the move played;
- the best move's predicted sequence;
- the rank of the move in KataGo's policy (its first instinct) and the policy's first move;
- that KaTrain took the move back in a teaching game.

The points lost are those of KentoGo's analysis (see analysis.played_moves); the best move, the
sequence and the policy come from the analysis of the position before the move. It is written as
KentoGo's part of the comment (see record.kentogo_comment).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.analysis.candidate_moves import policy_ranking, top_candidate
from kentogo.common.types import Move

LOSS_SHOWN = 0.5  # Smaller losses are not written (as KaTrain).
JAPANESE = "ja"
ENGLISH = "en"
KENTOGO_TEXTS = {
    JAPANESE: {
        "move": "第{number}手 {color} {point}",
        "loss": "損失: {loss:.1f}目",
        "best": "最善手: {point}（{score}、勝率 {winrate}）",
        "was_best": "最善手でした",
        "after": "打った後: {score}、勝率 {winrate}",
        "pv": "予想手順: {pv}",
        "policy_rank": "第一感: {rank}位（{probability:.1%}）",
        "policy_best": "第一感の1位: {point}（{probability:.1%}）",
        "taken_back": "KaTrainの待ったで戻した手です",
        "lead": "{color} {points:.1f}目リード",
        "even": "互角",
        "black": "黒",
        "white": "白",
        "pass": "パス",
        "root": "KentoGo {version} で解析",
    },
    ENGLISH: {
        "move": "Move {number}: {color} {point}",
        "loss": "Points lost: {loss:.1f}",
        "best": "Best move: {point} ({score}, win rate {winrate})",
        "was_best": "This was the best move",
        "after": "After the move: {score}, win rate {winrate}",
        "pv": "Predicted sequence: {pv}",
        "policy_rank": "Policy rank: {rank} ({probability:.1%})",
        "policy_best": "Policy's first move: {point} ({probability:.1%})",
        "taken_back": "KaTrain took this move back in a teaching game",
        "lead": "{color}+{points:.1f}",
        "even": "even",
        "black": "B",
        "white": "W",
        "pass": "pass",
        "root": "Analyzed by KentoGo {version}",
    },
}


@dataclass(frozen=True)
class CommentedMove:
    """The move that gets a comment.

    Attributes:
        number: Its move number.
        move: The move.
        points_lost: Its points lost (see analysis.played_moves), or None when not known.
        taken_back: KaTrain took it back in a teaching game.
    """

    number: int
    move: Move
    points_lost: float | None
    taken_back: bool = False


def comment_language(language: str) -> str:
    """Return the language of KentoGo's comments for a language code (KaTrain's "jp" or KentoGo's "ja": Japanese)."""
    return JAPANESE if language in ("jp", "ja") else ENGLISH


def kentogo_move_comment(
    commented: CommentedMove, before: dict, after: dict, size: tuple[int, int], language: str
) -> str:
    """Return KentoGo's comment on a move (see the module).

    Args:
        commented: The move.
        before: The analysis of the position before the move.
        after: The analysis of the position after the move.
        size: The board size (x, y).
        language: JAPANESE or ENGLISH.
    """
    texts = KENTOGO_TEXTS[language]
    move = commented.move
    lines = [texts["move"].format(number=commented.number, color=_color(move.color, texts), point=_point(move, texts))]
    lines += _best_lines(commented, before, size, texts)
    lines.append(texts["after"].format(**_standing(after.get("root") or {}, texts)))
    lines += _policy_lines(move, before, size, texts)
    if commented.taken_back:
        lines.append(texts["taken_back"])
    return "\n".join(lines)


def kentogo_root_comment(version: str, language: str) -> str:
    """Return KentoGo's comment on the root: the version of KentoGo that analyzed the game."""
    return KENTOGO_TEXTS[language]["root"].format(version=version)


def _best_lines(commented: CommentedMove, before: dict, size: tuple[int, int], texts: dict[str, str]) -> list[str]:
    """Return the lines of the points lost, the best move and its predicted sequence."""
    move = commented.move
    top = top_candidate(before, move.color, size)
    lines = []
    if top["move"] == move.gtp():
        lines.append(texts["was_best"])
    else:
        if commented.points_lost is not None and commented.points_lost > LOSS_SHOWN:
            lines.append(texts["loss"].format(loss=commented.points_lost))
        lines.append(texts["best"].format(point=top["move"], **_standing(top, texts)))
    if top.get("pv"):
        lines.append(texts["pv"].format(pv=f"{_color(move.color, texts)}{' '.join(top['pv'])}"))
    return lines


def _policy_lines(move: Move, before: dict, size: tuple[int, int], texts: dict[str, str]) -> list[str]:
    """Return the lines of the move's rank in the policy and the policy's first move."""
    ranking = policy_ranking(before, move.color, size)
    found = next(((index + 1, value) for index, (value, ranked) in enumerate(ranking) if ranked == move), None)
    lines = []
    if found is not None:
        lines.append(texts["policy_rank"].format(rank=found[0], probability=found[1]))
    if ranking and (found is None or found[0] != 1):
        value, first = ranking[0]
        lines.append(texts["policy_best"].format(point=_point(first, texts), probability=value))
    return lines


def _standing(values: dict, texts: dict[str, str]) -> dict[str, str]:
    """Return {score} and {winrate} of KataGo's values (black's side), such as "黒 2.1目リード" and "黒 55.0%"."""
    lead, winrate = values.get("scoreLead"), values.get("winrate")
    if lead is None:
        score = "-"
    elif round(lead, 1) == 0:
        score = texts["even"]
    else:
        score = texts["lead"].format(color=_color("B" if lead > 0 else "W", texts), points=abs(lead))
    if winrate is None:
        return {"score": score, "winrate": "-"}
    leader = _color("B" if winrate >= 0.5 else "W", texts)
    return {"score": score, "winrate": f"{leader} {max(winrate, 1 - winrate):.1%}"}


def _color(color: str, texts: dict[str, str]) -> str:
    """Return a player's name (black or white)."""
    return texts["black"] if color == "B" else texts["white"]


def _point(move: Move, texts: dict[str, str]) -> str:
    """Return a move's point, such as "Q16" (or pass)."""
    return texts["pass"] if move.is_pass else move.gtp()
