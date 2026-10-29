"""The prompt that asks an AI to explain the user's mistakes, made from the material of a game.

The same prompt is used for an AI called through its API and for the paste mode (the user
pastes it into the chat screen of any AI); the paste mode only adds a reminder at the end.
The AI answers in JSON (see answer_format), which commentary.answer reads.

The parts that do not depend on the game (the role of the AI, the first sentence, the
lines about the user, and the rules) come from a text file that the user can change (see
commentary.prompt_text). The rest is made here: the user's rank and opponent, how to read
the diagrams, the answer format, the table of losses, and for each move the facts that
KentoGo works out (the predicted sequence played on the board, captured stones, stones in
atari, liberties, candidate moves, and the diagrams), so that the AI does not have to work
them out itself.

The words that KentoGo adds are in the language of the prompt (see commentary.prompt_words):
Japanese, or English with the language of the answer (see commentary.language).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.commentary import diagram
from kentogo.commentary.language import CATEGORIES, CommentaryLanguage
from kentogo.commentary.material import GameMaterial, GroupInfo, MoveMaterial, PvStep
from kentogo.commentary.prompt_text import COLOR_PLACEHOLDER, PromptText
from kentogo.commentary.prompt_words import PromptWords, words_for
from kentogo.commentary.targets import targets_for
from kentogo.common.board import Point
from kentogo.common.types import GTP_COLUMNS, Move, opponent

# The rank of the opponent compared with the user, as chosen in the list of games.
RELATION_SAME = "same"
RELATION_HIGHER = "higher"
RELATION_LOWER = "lower"
RELATIONS = (RELATION_SAME, RELATION_HIGHER, RELATION_LOWER, "")

ZOOM_MARGIN = 3  # Points shown around the moves in a zoomed diagram.
ZOOM_MINIMUM = 9  # The smallest width and height of a zoomed diagram.


@dataclass(frozen=True)
class PlayerInfo:
    """What the user gives for one game.

    Attributes:
        rank: The user's rank at the time of the game, such as "18k" or "18級" ("" if not given).
        relation: One of RELATIONS: the rank of the opponent compared with the user.
    """

    rank: str = ""
    relation: str = ""


@dataclass(frozen=True)
class Prompt:
    """The prompt for one game.

    Attributes:
        system: The system prompt (the role of the AI).
        user: The message with the instructions and the data.
        paste_reminder: The reminder added at the end in the paste mode (see for_paste).
    """

    system: str
    user: str
    paste_reminder: str = ""

    def for_paste(self) -> str:
        """Return the whole prompt as one text, for the chat screen of an AI (which has no system prompt)."""
        return f"{self.system}\n\n{self.user}\n\n{self.paste_reminder}"


def build_prompt(material: GameMaterial, player: PlayerInfo, text: PromptText) -> Prompt:
    """Make the prompt for a game.

    Args:
        material: The material of the game (it must have at least one move).
        player: The user's rank and opponent for this game.
        text: The parts that the user can change (see commentary.prompt_text), with the language of the commentary.

    Returns:
        The prompt.
    """
    words = words_for(text.language.prompt)
    parts = [
        text.intro.replace(COLOR_PLACEHOLDER, words.color_name(material.my_color)),
        _about_me(player, text.about_me, words),
        f"{words.rules_heading}\n{text.rules}",
        words.diagram_legend,
        answer_format(words, text.language),
        f"{words.loss_heading}\n{loss_table(material, player.rank, words)}",
        f"{words.data_heading}\n" + "\n\n".join(_move_facts(material, move, words) for move in material.moves),
    ]
    return Prompt(text.system, "\n\n".join(part for part in parts if part), words.paste_reminder)


def answer_format(words: PromptWords, language: CommentaryLanguage) -> str:
    """Return the part that tells the AI how to answer: the JSON, its categories, and the language of the texts."""
    choices = [words.category_choice.format(name=name, words=w) for name, w in zip(CATEGORIES, words.category_names)]
    lines = [words.answer_format.format(categories="/".join(choices))]
    lines.append(words.answer_language.format(language=language.answer))
    return "\n".join(lines)


def _about_me(player: PlayerInfo, about_me: str, words: PromptWords) -> str:
    """Return the part about the user: the rank, the lines from the prompt file, and the opponent."""
    lines = [words.about_me]
    if words.rank(player.rank):
        lines.append(words.rank_line.format(rank=words.rank(player.rank)))
    lines += [line for line in about_me.splitlines() if line.strip()]
    lines.append(words.opponent_line.format(relation=_relation_text(player.relation, words)))
    return "\n".join(lines)


def _relation_text(relation: str, words: PromptWords) -> str:
    """Return the rank of the opponent compared with the user in words."""
    texts = {RELATION_SAME: words.relation_same, RELATION_HIGHER: words.relation_higher}
    return {**texts, RELATION_LOWER: words.relation_lower}.get(relation, words.relation_none)


def loss_table(material: GameMaterial, rank: str, words: PromptWords) -> str:
    """Return the table of how many moves lost at least each size of points, with the targets of the rank."""
    targets = targets_for(rank)
    lines = [words.loss_note, words.loss_header]
    for size, count in material.loss_counts:
        goal, limit = targets[size] if targets else ("-", "-")
        lines.append(words.loss_row.format(size=size, count=count, goal=goal, limit=limit))
    if targets is None:
        lines.append(words.no_targets)
    return "\n".join(lines)


def _move_facts(material: GameMaterial, move: MoveMaterial, words: PromptWords) -> str:
    """Describe one move with the facts that KentoGo worked out."""
    lines = _move_head(move, words) + [
        *_candidate_line(move, words),
        *_score_line(move, words),
        words.sequence_line.format(sequence=_sequence(move.pv, words)),
        words.facts_heading,
        *_step_lines(move.pv_steps, words),
        *_nearby_lines(move.nearby, words),
        *_reply_lines(move, words),
        *([words.notes_line.format(notes=move.notes)] if move.notes else []),
        *([words.katrain_line.format(text=move.katrain_text)] if move.katrain_text else []),
        words.before_diagram,
        _whole_diagram(material, move),
        words.zoom_diagram,
        _zoom_diagram(material, move),
        words.after_diagram,
        diagram.render(move.after_pv.stones, diagram.Region.whole(material.size)),
    ]
    return "\n".join(lines)


def _move_head(move: MoveMaterial, words: PromptWords) -> list[str]:
    """Return the heading and the first lines of a move."""
    color = words.color_name(move.played.color)
    played = _move_text(move.played, words)
    if move.taken_back:
        lines = [
            words.move_heading_taken_back.format(number=move.number, color=color),
            words.taken_back_line.format(move=played, loss=move.points_lost),
        ]
    else:
        lines = [
            words.move_heading.format(number=move.number, color=color),
            words.played_line.format(move=played, loss=move.points_lost),
        ]
    lines.append(words.best_line.format(best=move.best_move.gtp() if move.best_move else words.none))
    if move.last_move is not None:
        lines.append(words.last_move_line.format(move=_move_text(move.last_move, words)))
    return lines


def _candidate_line(move: MoveMaterial, words: PromptWords) -> list[str]:
    """Return the line of the candidate moves (none without analysis data)."""
    if not move.candidates:
        return []
    items = [words.candidate.format(point=point, loss=loss) for point, loss in move.candidates]
    return [words.candidates_line.format(items=words.list_separator.join(items))]


def _score_line(move: MoveMaterial, words: PromptWords) -> list[str]:
    """Return the line of the score after the move (none without analysis data)."""
    if move.score_after is None:
        return []
    leader = words.black if move.score_after >= 0 else words.white
    return [words.score_line.format(leader=leader, points=abs(move.score_after))]


def _reply_lines(move: MoveMaterial, words: PromptWords) -> list[str]:
    """Return the lines about the opponent's next move."""
    reply = move.reply
    if reply is None:
        return [words.reply_none]
    lines = [words.reply_line.format(move=_move_text(reply.move, words))]
    if reply.best_move:
        loss = words.reply_loss.format(loss=reply.points_lost) if reply.points_lost is not None else ""
        lines.append(words.reply_best_line.format(best=reply.best_move, loss=loss))
    if reply.pv:
        lines.append(words.reply_sequence_line.format(sequence=_sequence(reply.pv, words)))
    return lines


def _step_lines(steps: tuple[PvStep, ...], words: PromptWords) -> list[str]:
    """Return a line for each move of the predicted sequence that takes stones or puts stones in atari."""
    lines = []
    for number, step in enumerate(steps, start=1):
        captured = GroupInfo(opponent(step.move.color), step.captured, 0)
        events = [words.captures.format(group=_group_text(captured, words))] if step.captured else []
        events += [words.atari.format(group=_group_text(group, words)) for group in step.in_atari]
        if events:
            move = _move_text(step.move, words)
            lines.append(words.step_line.format(number=number, move=move, events=words.list_separator.join(events)))
    return lines or [words.no_steps]


def _nearby_lines(groups: tuple[GroupInfo, ...], words: PromptWords) -> list[str]:
    """Return the lines of the groups near the move, on the board before it."""
    if not groups:
        return []
    lines = [words.nearby_line.format(group=_group_text(group, words), liberties=group.liberties) for group in groups]
    return [words.nearby_heading, *lines]


def _whole_diagram(material: GameMaterial, move: MoveMaterial) -> str:
    """Return the diagram of the whole board before the move."""
    return diagram.render(move.before.stones, diagram.Region.whole(material.size), move.last_move, _marks(move))


def _zoom_diagram(material: GameMaterial, move: MoveMaterial) -> str:
    """Return the diagram of the part of the board around the played move and the best move."""
    points = [m.coord for m in (move.played, move.best_move) if m is not None and m.coord is not None]
    region = diagram.region_around(points, material.size, ZOOM_MARGIN, ZOOM_MINIMUM)
    return diagram.render(move.before.stones, region, move.last_move, _marks(move))


def _marks(move: MoveMaterial) -> dict[Point, str]:
    """Return the marks of the played move and the best move (the played move wins if they are the same)."""
    marks = {}
    if move.best_move is not None and move.best_move.coord is not None:
        marks[move.best_move.coord] = diagram.MARK_BEST
    if move.played.coord is not None:
        marks[move.played.coord] = diagram.MARK_PLAYED
    return marks


def _sequence(moves: tuple[Move, ...], words: PromptWords) -> str:
    """Return a sequence such as "黒Q16 → 白R14"."""
    return words.sequence_arrow.join(_move_text(move, words) for move in moves) if moves else words.none


def _move_text(move: Move, words: PromptWords) -> str:
    """Return a move such as "黒Q16" or "白パス"."""
    point = words.pass_move if move.is_pass else move.gtp()
    return words.move.format(color=words.color_name(move.color), point=point)


def _group_text(group: GroupInfo, words: PromptWords) -> str:
    """Return a group such as "白の石 C3,C4(2子)"."""
    return words.group.format(
        color=words.color_name(group.color), points=_points(group.stones), count=len(group.stones)
    )


def _points(points: tuple[Point, ...]) -> str:
    """Return points as GTP coordinates, such as "C3,C4" (at most 8, then "…")."""
    names = [f"{GTP_COLUMNS[x]}{y + 1}" for x, y in points[:8]]
    return ",".join(names) + (",…" if len(points) > 8 else "")
