"""Write the AI's commentary into the SGF file, in the same form as the user's script.

- Each explained move gets its commentary (see record.ai_comment), before the comment
  that was there (the user's notes and KaTrain's text are kept). A move that KaTrain took
  back gets it in its branch, so that the quiz shows it with its problem.
- The last move gets the review of the whole game. If the last move is also an explained
  move, it gets both: the commentary first, then the review.
- Any AI commentary that was there before (on the main line and on the branches next to it)
  is removed first, so that a new commentary replaces the old one.
- The words that KentoGo writes around the AI's answer (the labels, the table of losses, the
  names of the categories) are in the language of the screens (see commentary.language).
- Before the file is written, a copy is kept as "<file>.<date-time>.bak" (the same as the script).
  The file is written as UTF-8 (CA[UTF-8]), through a temporary file, so that a failure
  never leaves a half-written file.

This is the only module that writes SGF files.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pysgf import GoNode

from kentogo.commentary.answer import Answer
from kentogo.commentary.language import CommentLabels
from kentogo.commentary.material import GameMaterial, MoveMaterial, position_node, problem_node
from kentogo.commentary.targets import targets_for
from kentogo.common import sgf
from kentogo.record.ai_comment import compose_comment, split_ai_comment

# The fields of the answer, in the order they are written (their labels are in CommentLabels).
_MOVE_FIELDS = ("situation", "category", "what_happened", "aim", "lesson")
_SUMMARY_FIELDS = ("category_counts", "main_issue", "next_focus", "loss_comparison")


@dataclass(frozen=True)
class WriteResult:
    """What was written.

    Attributes:
        backup: The copy of the file before it was written.
        moves: The numbers of the moves that got a commentary.
    """

    backup: Path
    moves: tuple[int, ...]


def write_commentary(
    path: Path,
    material: GameMaterial,
    answer: Answer,
    rank: str,
    labels: CommentLabels = CommentLabels(),
    now: Callable[[], datetime] = datetime.now,
) -> WriteResult:
    """Write the AI's answer into an SGF file, keeping a copy of the file first.

    Args:
        path: The SGF file. It is read again here, so that changes since the material was made are kept.
        material: The material that the answer is about.
        answer: The checked answer (answer.ok must be True).
        rank: The user's rank, for the targets in the review.
        labels: The words written around the answer, in the language of the screens.
        now: Returns the current time, for the name of the copy (tests give a fixed time).

    Returns:
        The copy and the moves that got a commentary.

    Raises:
        ValueError: If the answer has errors, or the moves in the file are not the moves of the material.
        OSError: If the file cannot be read, copied or written.
    """
    if not answer.ok:
        raise ValueError("the answer has errors")
    root = sgf.load_game(path)
    nodes = [node for node in sgf.main_line(root)[1:] if sgf.node_move(node) is not None]
    targets = _target_nodes(nodes, material)
    texts = {
        id(targets[move.number]): move_comment_text(move, answer.moves[move.number], labels) for move in material.moves
    }
    _clear_and_set(nodes, texts, review_comment_text(material, rank, answer.summary, labels), labels)
    backup = backup_file(path, now())
    root.set_property("CA", "UTF-8")
    _write_text(path, root.sgf())
    return WriteResult(backup, tuple(sorted(move.number for move in material.moves)))


def _target_nodes(nodes: list[GoNode], material: GameMaterial) -> dict[int, GoNode]:
    """Return the node of each explained move (in the game, or a branch for a move taken back), by number.

    Raises:
        ValueError: If a move is not in the file any more (the file was changed since the material was made).
    """
    targets = {}
    for move in material.moves:
        node = problem_node(nodes, move.number, move.played)
        if node is None or any(node is game_node for game_node in nodes) == move.taken_back:
            raise ValueError(f"move {move.number} in the file is not {move.played.gtp()}: the file was changed")
        targets[move.number] = node
    return targets


def _clear_and_set(nodes: list[GoNode], texts: dict[int, str], review: str, labels: CommentLabels) -> None:
    """Put the commentary on the nodes in texts (by id), and remove old AI parts from all other moves.

    The moves of the game and the branches next to them are visited; the last move of the game gets the review.
    """
    for number in range(1, len(nodes) + 2):
        parent = position_node(nodes, number)
        for node in parent.children if parent is not None else ():
            last = number == len(nodes) and node is nodes[-1]
            _set_comment(node, texts.get(id(node), ""), review if last else "", labels)


def move_comment_text(move: MoveMaterial, fields: dict[str, str], labels: CommentLabels = CommentLabels()) -> str:
    """Return the commentary of one move: the first line with the moves and the loss, then one line for each field."""
    best = move.best_move.gtp() if move.best_move else labels.no_best
    played = labels.taken_back if move.taken_back else labels.actual
    lines = [labels.move_line.format(played=played, move=move.played.gtp(), best=best, loss=move.points_lost)]
    values = {**fields, "category": labels.category_name(fields.get("category", ""))}
    lines += [f"{labels.bullet}{getattr(labels, name)}: {values[name]}" for name in _MOVE_FIELDS if values.get(name)]
    return "\n".join(lines)


def review_comment_text(
    material: GameMaterial, rank: str, summary: dict[str, str], labels: CommentLabels = CommentLabels()
) -> str:
    """Return the review of the whole game: the explained moves, the counts of losses, and the AI's review."""
    color = labels.color_name(material.my_color)
    by_loss = sorted(material.moves, key=lambda move: (-move.points_lost, move.number))
    lines = [labels.review_title.format(count=len(by_loss))]
    for move in by_loss:
        best = move.best_move.gtp() if move.best_move else labels.no_best
        taken_back = f" {labels.taken_back}" if move.taken_back else ""
        values = {"number": move.number, "color": color, "taken_back": taken_back, "loss": move.points_lost}
        lines.append(labels.review_move.format(**values, best=best))
    lines += ["", *_loss_lines(material, rank, labels), ""]
    lines += [
        f"{labels.bullet}{getattr(labels, name)}: {summary[name]}" for name in _SUMMARY_FIELDS if summary.get(name)
    ]
    return "\n".join(lines)


def backup_file(path: Path, when: datetime) -> Path:
    """Copy a file to "<file>.<date-time>.bak" (with "-2", "-3"... if that name is taken), and return the copy."""
    stamp = when.strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    number = 1
    while backup.exists():
        number += 1
        backup = path.with_name(f"{path.name}.{stamp}-{number}.bak")
    shutil.copy2(path, backup)
    return backup


def _loss_lines(material: GameMaterial, rank: str, labels: CommentLabels) -> list[str]:
    """Return the counts of losses with the targets of the rank, as the script writes them."""
    targets = targets_for(rank)
    lines = [labels.loss_title, labels.loss_note]
    for size, count in material.loss_counts:
        extra = labels.loss_targets.format(goal=targets[size][0], limit=targets[size][1]) if targets else ""
        lines.append(labels.bullet + labels.loss_line.format(size=size, count=count, targets=extra))
    if targets is None:
        lines.append(labels.no_targets.format(rank=rank or labels.no_rank))
    return lines


def _set_comment(node: GoNode, move_text: str, review_text: str, labels: CommentLabels) -> None:
    """Replace the AI parts of the comment of a node (the rest of the comment is kept)."""
    old = str(node.get_property("C", ""))
    new = compose_comment(split_ai_comment(old).rest, move_text, review_text, labels.move_header, labels.review_header)
    if new == old:
        return
    if new:
        node.set_property("C", new)
    else:
        node.clear_property("C")


def _write_text(path: Path, text: str) -> None:
    """Write a text file as UTF-8 through a temporary file in the same folder, then put it in place."""
    temporary = path.with_name(f".{path.name}.writing")
    with open(temporary, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)
    os.replace(temporary, path)
