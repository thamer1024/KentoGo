"""The lines of the prompt about the shapes around a mistake (see commentary.move_facts).

The facts are written as observations only: the name of each shape with the stones it is named from,
what each move does, where the opponent plays after the best move in the predicted sequence, the
cutting points and the groups that were aimed at. Whether the best move was sente is left to the AI,
as the sequence is only cut off somewhere and does not tell it.
"""

from __future__ import annotations

from kentogo.commentary.diagram import Region
from kentogo.commentary.move_facts import GroupInfo, MoveFacts, ShapedMove
from kentogo.commentary.prompt_words import PromptWords
from kentogo.common.board import Point
from kentogo.common.places import line_of, region_of
from kentogo.common.shapes import CUT, TSUKE, WEDGE, Shape
from kentogo.common.tactics import EMPTY_TRIANGLE, KO, LADDER, PON_NUKI, SELF_ATARI
from kentogo.common.types import GTP_COLUMNS, Move, opponent

NEAR_DISTANCE = 3  # The opponent's next move this close to the best move answers it (else it plays elsewhere).
MOST_POINTS = 8  # At most this many points are written in a list.
THEIR_STONES = (CUT, WEDGE, TSUKE)  # The shapes named from the opponent's stones (the others from own stones).


def fact_lines(facts: MoveFacts, size: int, zoom: Region, words: PromptWords) -> list[str]:
    """Return the lines of the facts about the shapes around a mistake.

    Args:
        facts: The facts.
        size: The size of the board.
        zoom: The part of the board of the zoomed diagram (the cutting points are told only there).
        words: The words of the prompt.
    """
    lines = []
    if facts.last_move is not None:
        lines.append(words.last_move_shape.format(**_shaped(facts.last_move, size, words)))
    lines.append(words.played_shape.format(**_shaped(facts.played, size, words)))
    if facts.best is not None:
        lines.append(words.best_shape.format(**_shaped(facts.best, size, words)))
    lines.append(words.game_heading)
    lines += [words.game_line.format(**_shaped(move, size, words)) for move in facts.game]
    lines.append(words.pv_heading)
    lines += [
        words.pv_line.format(number=number, **_shaped(move, size, words))
        for number, move in enumerate(facts.pv, start=1)
    ]
    lines += _next_move_lines(facts, size, words)
    lines.append(_cuts_line(facts, zoom, words))
    return lines + _aimed_lines(facts.aimed_at, words)


def _shaped(move: ShapedMove, size: int, words: PromptWords) -> dict[str, str]:
    """Return the values of a line about one move: {move} with its place, and {shape}."""
    parts = [_shape_text(shape, move.move.color, words) for shape in move.shapes]
    parts += _effect_texts(move, words)
    shape = words.shape_separator.join(parts) if parts else words.no_shape
    return {"move": placed_move_text(move.move, size, words), "shape": shape}


def _shape_text(shape: Shape, color: str, words: PromptWords) -> str:
    """Return a shape such as "キリ(白O3,白P4を切る)" (the stones from the left)."""
    owner = opponent(color) if shape.name in THEIR_STONES else color
    stones = ",".join(words.move.format(color=words.color_name(owner), point=_point(p)) for p in sorted(shape.stones))
    return words.shape_names[shape.name].format(stones=stones)


def _effect_texts(move: ShapedMove, words: PromptWords) -> list[str]:
    """Return what a move does: the stones it takes, the opponent's groups it puts in atari, and the rest."""
    found = []
    if move.captured:
        captured = group_text(GroupInfo(opponent(move.move.color), move.captured, 0), words)
        effect = words.pon_nuki_effect if PON_NUKI in move.effects else words.capture_effect
        found.append((words.ko_effect if KO in move.effects else effect).format(group=captured))
    theirs = [group for group in move.in_atari if group.color != move.move.color]
    found += [words.atari_effect.format(group=group_text(group, words)) for group in theirs]
    others = {LADDER: words.ladder_effect, EMPTY_TRIANGLE: words.empty_triangle_effect}
    others[SELF_ATARI] = words.self_atari_effect
    return found + [others[name] for name in move.effects if name in others]


def _next_move_lines(facts: MoveFacts, size: int, words: PromptWords) -> list[str]:
    """Return the line about where the opponent plays after the best move in the predicted sequence."""
    if facts.reply_distance is None or len(facts.pv) < 2:
        return []
    reply = facts.pv[1].move
    values = {
        "color": words.color_name(reply.color),
        "move": _placed(reply.gtp(), reply.coord, size, words),
        "distance": facts.reply_distance,
    }
    text = words.next_near if facts.reply_distance <= NEAR_DISTANCE else words.next_far
    return [text.format(**values)]


def _cuts_line(facts: MoveFacts, zoom: Region, words: PromptWords) -> str:
    """Return the line of the user's cutting points in the zoomed part, before and after the moves."""

    def inside(points: tuple[Point, ...]) -> str:
        shown = tuple(p for p in points if zoom.left <= p[0] <= zoom.right and zoom.bottom <= p[1] <= zoom.top)
        return points_text(shown) if shown else words.cuts_none

    return words.cuts_line.format(
        color=words.color_name(facts.played.move.color),
        before=inside(facts.cuts_before),
        game=inside(facts.cuts_after_game),
        pv=inside(facts.cuts_after_pv),
    )


def _aimed_lines(groups: tuple[GroupInfo, ...], words: PromptWords) -> list[str]:
    """Return the lines of the user's groups that were aimed at (none without them)."""
    if not groups:
        return []
    lines = [words.nearby_line.format(group=group_text(group, words), liberties=group.liberties) for group in groups]
    return [words.aimed_heading, *lines]


def placed_move_text(move: Move, size: int, words: PromptWords) -> str:
    """Return a move with its place, such as "黒R11(右辺,3線)" (a pass has no place)."""
    if move.coord is None:
        return move_text(move, words)
    return _placed(move_text(move, words), move.coord, size, words)


def _placed(text: str, point: Point | None, size: int, words: PromptWords) -> str:
    """Return a move or a point written as text with the place of the point after it (nothing for a pass)."""
    if point is None:
        return text
    region = words.region_names[region_of(point, size)]
    return words.placed_move.format(move=text, region=region, line=line_of(point, size))


def move_text(move: Move, words: PromptWords) -> str:
    """Return a move such as "黒Q16" or "白パス"."""
    point = words.pass_move if move.is_pass else move.gtp()
    return words.move.format(color=words.color_name(move.color), point=point)


def group_text(group: GroupInfo, words: PromptWords) -> str:
    """Return a group such as "白の石 C3,C4(2子)"."""
    return words.group.format(
        color=words.color_name(group.color), points=points_text(group.stones), count=len(group.stones)
    )


def points_text(points: tuple[Point, ...]) -> str:
    """Return points as GTP coordinates, such as "C3,C4" (at most MOST_POINTS, then "…")."""
    names = [_point(point) for point in points[:MOST_POINTS]]
    return ",".join(names) + (",…" if len(points) > MOST_POINTS else "")


def _point(point: Point) -> str:
    """Return a point as a GTP coordinate, such as "C3"."""
    return f"{GTP_COLUMNS[point[0]]}{point[1] + 1}"
