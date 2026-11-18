"""The texts of the territory counting practice."""

from __future__ import annotations

from kentogo.common.types import Move
from kentogo.gui import texts
from kentogo.seichi.arrangement import FillStep
from kentogo.seichi.count_check import CountCheck


def fill_step_text(step: FillStep | None, number: int, total: int) -> str:
    """Return the line that tells one step of the computer's seichi (None: the board before it)."""
    if step is None:
        return texts.text("seichi_steps", number=0, total=total, step=texts.text("seichi_steps_start"))
    names = [Move(step.color or "B", point).gtp() for point in step.points]
    color = texts.color_name(step.color) if step.color else ""
    if step.kind == "capture":
        line = texts.text("seichi_step_capture", color=color, count=len(names))
    elif step.kind == "place":
        line = texts.text("seichi_step_place", color=color, point=names[0])
    elif step.kind == "move":
        line = texts.text("seichi_step_move", color=color, source=names[0], target=names[1])
    else:
        line = _exchange_text(step, names, color)
    return texts.text("seichi_steps", number=number, total=total, step=line)


def _exchange_text(step: FillStep, names: list[str], color: str) -> str:
    """Return the words of a step that exchanges stones with the other player (a color change or a swap)."""
    new = texts.color_name("W" if step.color == "B" else "B")
    if step.kind == "swap":
        return texts.text("seichi_step_swap", color=color, new=new, source=names[0], target=names[1])
    if len(names) == 1:
        return texts.text("seichi_step_recolor", color=color, new=new, point=names[0])
    return texts.text("seichi_step_exchange", color=color, new=new, source=names[0], target=names[1])


def lead_text(lead: float, komi: float | None = None) -> str:
    """Return who is ahead by how many points (black's lead; with komi, who wins after komi)."""
    prefix = "lead_" if komi is None else "lead_komi_"
    key = prefix + ("black" if lead > 0 else "white" if lead < 0 else "even")
    return texts.text(key, points=f"{abs(lead):g}", komi=f"{komi:g}" if komi is not None else "")


def count_check_text(check: CountCheck, komi: float) -> str:
    """Return the result of 整地終了: right or wrong, the territory on the board, and the right one with komi."""
    seichi = texts.text("count_seichi_ok")
    if not check.passed:
        seichi = texts.text("count_seichi_wrong", black=check.counted.black, white=check.counted.white)
    left = sum(check.prisoners_left.values())
    if left:
        seichi += texts.text("count_prisoners_left", count=left)
    right = check.right
    answer = texts.text(
        "count_answer", black=right.black, white=right.white, result=lead_text(right.black - right.white - komi, komi)
    )
    verdict = texts.text("count_passed" if check.passed else "count_failed")
    return "\n".join([verdict, seichi, answer])
