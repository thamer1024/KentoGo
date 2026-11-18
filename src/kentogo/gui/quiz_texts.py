"""The texts of the mistake problems: the problem, the result of an answer, and what the start screen tells."""

from __future__ import annotations

from pathlib import Path

from kentogo.common.tactics import SURE
from kentogo.common.types import Move
from kentogo.gui import texts
from kentogo.gui.source_texts import TEXTS
from kentogo.katago.move_value import URGENT, MoveValue, kind_of
from kentogo.mistakes.extract import PUNISH, SHARED
from kentogo.mistakes.problem import Problem
from kentogo.quiz.collect import SkippedGame
from kentogo.quiz.limit_offer import LimitOffer
from kentogo.quiz.score import Comparison, compare_with_actual
from kentogo.quiz.session import AnswerResult
from kentogo.review.record import AnswerRecord


def skipped_text(skipped: dict[str, int]) -> str:
    """Return the line about the games that gave no problems, or "" if there are none.

    Args:
        skipped: How many games gave no problems, for each reason (such as "no_analysis").
    """
    details = []
    for reason, count in sorted(skipped.items()):
        key = f"skipped_{reason}"
        details.append(texts.text(key, count=count) if key in TEXTS else f"{reason} {count}")
    return texts.text("splash_skipped", details=texts.list_text(details)) if details else ""


def skipped_games_text(games: list[SkippedGame]) -> str:
    """Return one line for each game that gave no problems, to show in a dialog.

    Args:
        games: The games that gave no problems.
    """
    lines = []
    for game in games:
        key = f"skipped_game_{game.reason}"
        lines.append(
            texts.text(key, name=game.name, detail=game.detail) if key in TEXTS else f"{game.name}: {game.reason}"
        )
    return "\n".join(lines)


def history_text(previous: list[AnswerRecord]) -> str:
    """Return the line about the earlier answers to a problem: how many times, and the last result.

    Args:
        previous: The earlier answers to the problem, the oldest first.
    """
    if not previous:
        return texts.text("history_first")
    last = previous[-1].correct
    if last is None:
        result = texts.text("history_not_judged")
    else:
        result = texts.text("history_correct") if last else texts.text("history_wrong")
    return texts.text("history_again", count=len(previous) + 1, last=result)


# The kinds of problems: their texts and colors (light colors, easy to read on the dark panel).
KIND_TITLES = {"": ("kind_mistake", "6cc0ff"), PUNISH: ("kind_punish", "ffb74d"), SHARED: ("kind_shared", "80deea")}


KIND_TITLE_SIZE = "20sp"


def problem_info(problem: Problem, index: int, total: int) -> str:
    """Return the text about the problem: its kind (big and colored), the game, the move, the player, the count.

    Args:
        problem: The problem as it is shown.
        index: The number of the problem, starting from 1.
        total: The number of problems.
    """
    info = texts.text(
        "problem_info",
        game=Path(problem.sgf_path).stem,
        move_number=problem.move_number,
        color=texts.color_name(problem.position.next_color),
        index=index,
        total=total,
    )
    hint = punishment_hint(problem)
    info = f"{info}{texts.gap()}{hint}" if hint else info
    return f"{kind_title(problem)}\n{info}"


def kind_title(problem: Problem) -> str:
    """Return the kind of a problem in big colored letters, such as 失敗した手の練習 or 咎める手の演習."""
    key, color = KIND_TITLES.get(problem.punishment, KIND_TITLES[""])
    return f"[size={KIND_TITLE_SIZE}][b][color={color}]{texts.text(key)}[/color][/b][/size]"


def punishment_hint(problem: Problem) -> str:
    """Return the hint of a punishment problem (or of a point that both missed), or "" for other problems."""
    if problem.punishment == PUNISH:
        return texts.text("punish_hint", loss=f"{problem.opponent_loss or 0:.1f}")
    if problem.punishment == SHARED:
        return texts.text("shared_hint")
    return ""


def _comparison_line(comparison: Comparison, move: Move, other: bool, loss: float | None) -> str:
    """Return the line of the losses: the game move against the answer, or against another move (other)."""
    if not other:
        loss = comparison.answer_loss
    elif loss is None:
        return texts.text("comparison_unknown", actual=comparison.actual_loss, move=move.gtp())
    shown = compare_with_actual(comparison.actual_loss, loss)
    return texts.text(
        "comparison",
        actual=shown.actual_loss,
        move=move.gtp(),
        answer=shown.answer_loss,
        improvement=shown.improvement,
        ratio=shown.recovered_ratio,
    )


def result_text(
    problem: Problem,
    result: AnswerResult,
    waiting_reason: str = "",
    sequence: tuple[Move, float | None] | None = None,
    show_verdict: bool = True,
    tactics: tuple[str, ...] = (),
    value: MoveValue | None = None,
    best_waiting: bool = False,
    value_running: bool = False,
) -> str:
    """Return the text about the result of an answer.

    Args:
        problem: The problem in the original direction and colors.
        result: The result of the answer.
        waiting_reason: Why the answer is not judged yet (used only when result.correct is None),
            such as text("evaluating").
        sequence: The first move of the shown sequence and its loss (None if unknown), when it is
            not the answer: the line of the losses then tells about that move (see QuizSession.sequence_loss).
        show_verdict: False to leave out whether the answer is correct (or why it is not judged yet),
            while another sequence than the answer's is shown.
        tactics: What the best move does on the board (see common.tactics), shown once the answer is judged.
        value: What KataGo found that the best move does (see katago.move_value), or None (not read yet).
        best_waiting: True while the best move (problem.best_move) is being calculated: it is told instead of "不明".
        value_running: True while KataGo is reading what the best move does: it is told after the other lines.

    Returns:
        Whether the answer is correct, the losses, the moves, what the best move does, and the legend of the marks.
    """
    unknown = texts.text("sequence_waiting") if best_waiting else texts.text("unknown_move")
    best = problem.best_move.gtp() if problem.best_move else unknown
    shown_move, shown_loss = sequence if sequence is not None else (result.answer, None)
    moves = texts.text("moves", answer=result.answer.gtp(), actual=problem.actual_move.gtp(), best=best)
    legend = texts.text("legend")
    if result.correct is None:
        waiting = [texts.text("not_judged", reason=waiting_reason)] if show_verdict else []
        return "\n".join([*waiting, moves, legend])
    losses = _comparison_line(result.comparison, shown_move, sequence is not None, shown_loss)
    verdict = [texts.text("correct") if result.correct else texts.text("wrong")] if show_verdict else []
    what = tactics_text(problem.best_move, tactics, value)
    running = [texts.text("best_value_running")] if value_running else []
    return "\n".join([*verdict, losses, moves, *([what] if what else []), *running, legend])


def tactics_text(best_move: Move | None, names: tuple[str, ...], value: MoveValue | None = None) -> str:
    """Return what the best move does, such as "最善 Q4：アタリ、シチョウ、ハネ？、急場？（…）" ("" if nothing is known).

    The guesses (see common.tactics.GUESSED) are marked with a question mark; KataGo's findings (value)
    come after the others.
    """
    words = [texts.text(f"tactic_{name}") for name in names]
    words = [
        word if name in SURE else texts.text("tactic_guess", name=word) for name, word in zip(names, words, strict=True)
    ]
    words += value_words(value) if value is not None else []
    if best_move is None or not words:
        return ""
    return texts.text("best_move_tactics", move=best_move.gtp(), names=texts.list_text(words))


MIN_VALUE_POINTS = 1.0  # The size of a move (urgent or big) is told when leaving it loses at least this.


def value_words(value: MoveValue) -> list[str]:
    """Return the words of KataGo's findings: the stones killed or saved, and whether the move is urgent or big."""
    words = [texts.text("value_kill", count=value.killed)] if value.killed else []
    words += [texts.text("value_save", count=value.saved)] if value.saved else []
    if value.points >= MIN_VALUE_POINTS:
        key = "value_urgent" if kind_of(value) == URGENT else "value_big"
        words.append(texts.text(key, points=f"{value.points:.1f}"))
    return words


def limit_offer_text(offer: LimitOffer) -> str:
    """Return the question of the offer to set or lower the limit of a correct answer's loss."""
    current = texts.text("limit_none") if offer.current == 0 else f"{offer.current:g}"
    return texts.text(
        "limit_offer",
        total=offer.total,
        correct=offer.correct,
        average=f"{offer.average:.1f}",
        current=current,
        proposed=f"{offer.proposed:g}",
    )
