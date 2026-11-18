"""The texts of the local fight problems."""

from __future__ import annotations

from pathlib import Path

from kentogo.gui import quiz_texts, texts
from kentogo.mistakes.local_fight import KIND_BOUNDARY, LocalFight
from kentogo.quiz.fight_follow import END_PASS, FollowEnd
from kentogo.quiz.fight_judge import FightOutcome
from kentogo.quiz.fight_lines import AI_CALCULATING, AI_FAILED, LINE_AI, LINE_STRONG, FightLines

FIGHT_TITLE_COLOR = "ce93d8"  # The local fight problems (see fight_info).


def fight_info(fight: LocalFight, index: int, total: int) -> str:
    """Return the text about a local fight problem: its kind (big and colored), the game, the move, the count.

    Args:
        fight: The fight.
        index: The number of the fight, starting from 1.
        total: The number of fights.
    """
    key = "fight_kind_boundary" if fight.kind == KIND_BOUNDARY else "fight_kind_life_death"
    title = f"[size={quiz_texts.KIND_TITLE_SIZE}][b][color={FIGHT_TITLE_COLOR}]{texts.text(key)}[/color][/b][/size]"
    info = texts.text(
        "problem_info",
        game=Path(fight.sgf_path).stem,
        move_number=fight.move_number,
        color=texts.color_name(fight.position.next_color),
        index=index,
        total=total,
    )
    return f"{title}\n{info}"


def fight_outcome_text(outcome: FightOutcome) -> str:
    """Return how a local fight ended, with the points lost since the start when they are known."""
    verdict = texts.text(f"fight_{outcome.kind}")
    if outcome.score_loss is None:
        return verdict
    return f"{verdict}\n{texts.text('fight_score_loss', loss=outcome.score_loss)}"


def fight_line_text(lines: FightLines, seconds: int = 0) -> str:
    """Return the line about the sequence shown after a local fight, and whether the AIs' sequence is coming.

    Args:
        lines: The sequences of the fight.
        seconds: How long KataGo has been making the sequence (shown while it is coming).
    """
    shown = texts.text(
        "fight_line",
        name=texts.text(f"fight_line_{lines.name}"),
        index=lines.selected + 1,
        count=lines.count,
        step=lines.step,
        total=lines.length,
    )
    if lines.name == LINE_AI and lines.ai_state == AI_CALCULATING:
        return f"{shown}\n{texts.text('fight_line_ai_calculating', seconds=seconds)}"
    if lines.name == LINE_AI and lines.ai_state == AI_FAILED:
        return f"{shown}\n{texts.text('fight_line_ai_failed')}"
    if lines.name == LINE_AI and lines.ai_end is not None:
        return f"{shown}\n{follow_end_text(lines.ai_end)}"
    if lines.name == LINE_STRONG:
        return f"{shown}\n{texts.text('fight_strong_note')}\n{_strong_state_text(lines, seconds)}"
    return shown


def _strong_state_text(lines: FightLines, seconds: int) -> str:
    """Return how the sequence of the strongest AI stands: coming (for how long), failed, or why it ended."""
    if lines.strong_state == AI_CALCULATING:
        return texts.text("fight_strong_calculating", seconds=seconds)
    if lines.strong_state == AI_FAILED:
        return texts.text("fight_strong_failed")
    return follow_end_text(lines.strong_end)


def follow_end_text(end: FollowEnd) -> str:
    """Return why the sequence of the AIs ended (a pass is told as a side that left the fight)."""
    key = "left" if end.reason == END_PASS else end.reason
    color = texts.color_name(end.color) if end.color else ""
    other = texts.color_name("W" if end.color == "B" else "B") if end.color else ""
    return texts.text(f"fight_follow_{key}", color=color, other=other, black=end.black, white=end.white)
