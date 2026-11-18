"""The names of the sequences, the notes and the standings, shown by the quiz and by the screen of the games."""

from __future__ import annotations

from kentogo.gui import texts
from kentogo.gui.source_texts import TEXTS
from kentogo.katago.estimate import Standing


def sequence_name(source: str) -> str:
    """Return the name of a sequence from its source, such as "katrain" or "katago"."""
    key = f"source_{source}"
    return texts.text(key) if key in TEXTS else source


def short_sequence_name(source: str) -> str:
    """Return the short name of a sequence from its source, as in the order of Tab (such as 段級位の応手)."""
    key = f"short_{source}"
    return texts.text(key) if key in TEXTS else source


def sequence_order_text(choices: list[tuple[str, str]], selected: int, seconds: int = 0) -> str:
    """Return the line that shows the order of the sequences for Tab, with the shown one marked.

    A sequence that KataGo is still calculating, or could not calculate, is shown with its status.

    Args:
        choices: (source, status) of each sequence in order. status is "" when the sequence
            is ready, "waiting" while KataGo is calculating it, or "failed".
        selected: The index of the shown sequence.
        seconds: How long KataGo has been calculating, shown with the sequences it is calculating.
    """
    names = []
    for index, (source, status) in enumerate(choices):
        name = short_sequence_name(source)
        if status:
            name = texts.text(f"short_{status}", name=name, seconds=seconds)
        names.append(f"[color=f2c94c][b]▶{name}[/b][/color]" if index == selected else name)
    return texts.text("sequence_order", names=" → ".join(names))


def sequence_text(source: str, index: int, count: int, step: int, total: int, status: str = "") -> str:
    """Return the text about the sequence that is shown: what it is, and how far it is played.

    Args:
        source: Where the sequence came from, such as "katrain" or "katago".
        index: The number of the sequence, starting from 1.
        count: The number of sequences.
        step: How many moves of the sequence are shown.
        total: The number of moves in the sequence.
        status: "" when the sequence is ready, "waiting" while KataGo is calculating it, or "failed".
    """
    key = f"explain_{source}"
    explanation = texts.text(key) if key in TEXTS else ""
    name = sequence_name(source)
    shown = texts.text("sequence", name=name, explanation=explanation, index=index, count=count, step=step, total=total)
    if status:
        # The first two lines (the name and the explanation), and what KataGo is doing instead of the moves.
        shown = "\n".join(shown.split("\n")[:2] + [texts.text(f"sequence_{status}")])
    return shown


def notes_text(notes: str, ai_comment: str = "") -> str:
    """Return the AI commentary and the notes to show ("" when there are none).

    Args:
        notes: The user's notes (already rewritten if the board is changed, see quiz.notes_transform).
        ai_comment: The AI commentary (already rewritten in the same way), shown first under a heading.
    """
    parts = ([f"{texts.text('ai_commentary')}\n{ai_comment}"] if ai_comment else []) + ([notes] if notes else [])
    return "\n\n".join(parts)


def quick_standing_text(lead: float) -> str:
    """Return the rough standing of a position read shallowly (see katago.quick_reading)."""
    return texts.text("quick_standing", leader=texts.color_name("B" if lead >= 0 else "W"), ahead=abs(lead))


def rough_standing_text(lead: float, moves: int) -> str:
    """Return the rough standing of a position some moves into a sequence (black's lead, see quiz.quick_areas)."""
    return texts.text(
        "rough_standing", leader=texts.color_name("B" if lead >= 0 else "W"), ahead=abs(lead), moves=moves
    )


def standing_text(standing: Standing, moves: int) -> str:
    """Return the standing at the end of a sequence of some moves."""
    lead = standing.end.lead
    return texts.text("standing", leader=texts.color_name("B" if lead >= 0 else "W"), ahead=abs(lead), moves=moves)


def standing_gain_text(standing: Standing) -> str:
    """Return how the standing at the end of a sequence compares with the game after the same number of moves."""
    return texts.text("standing_gain", player=texts.color_name(standing.color), gain=standing.gain)
