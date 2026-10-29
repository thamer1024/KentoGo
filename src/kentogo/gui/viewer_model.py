"""What the screen that shows a game draws and writes, without Kivy (so that it can be tested).

The screen keeps the record of the game and where it is (a Browse); this module turns
them into the board view and the texts, and moves through the game and the sequences.

At a move, the screen can show sequences in place of the move: KaTrain's predicted
sequence (from the position before the move, starting with the best move), then the other
branches of the SGF file at that move. Moving forward and back (Space, the arrows) follows
the game, or the sequence while one is shown. Tab goes from the game to the first sequence
(its first move replaces the move of the game), then to the next ones, and after the last
one back to the game at the move where the sequences branch off.

The comparison model's best sequence at a move comes last, once the screen has asked for it
(the screen keeps these sequences, by position, and passes them as added).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from kentogo.common.types import Move, moves_from_gtp
from kentogo.gui import texts
from kentogo.gui.board_view import MARK_ACTUAL, MARK_BEST, MARK_COMPARE, BoardView, collect_marks, make_board_view
from kentogo.mistakes.problem import SOURCE_KATAGO_COMPARE, SOURCE_KATRAIN, Variation
from kentogo.record.game_record import GameRecord, move_commentary, next_position
from kentogo.record.library import GameFile

AI_MARK = "★"  # Put before the name of a game with an AI commentary in the list.

SOURCE_BRANCH = "sgf_branch"  # Another branch of the SGF file at the move.
SOURCE_COMPARE = SOURCE_KATAGO_COMPARE  # The comparison model's best sequence, the same name as in the quiz.

Added = Mapping[int, Variation]  # The comparison model's sequences, by position.
NONE_ADDED: Added = MappingProxyType({})


@dataclass(frozen=True)
class Browse:
    """Where the screen is in a game.

    Attributes:
        position: The position of the game (see record.game_record).
        variation: The index of the sequence shown in place of the move of the position
            (see variations_at), or None when the game itself is shown.
        step: How many moves of the sequence are shown (from 1: the first move replaces the move of the game).
    """

    position: int = 0
    variation: int | None = None
    step: int = 0


def board_view(record: GameRecord, position: int) -> BoardView:
    """Return the board at a position, with the last move and the best move that KaTrain gave for it."""
    state = record.state(position)
    move = record.move_at(position)
    last = move.move.coord if move is not None else None
    best = None
    if move is not None and move.katrain is not None and move.katrain.best_move:
        best = Move.from_gtp(move.katrain.best_move, move.move.color)
        if best.coord == last:
            best = None  # The move played was the best: only the mark of the last move.
    return BoardView(record.size, dict(state.stones), last_move=last, marks=collect_marks([(best, MARK_BEST)]))


def position_text(record: GameRecord, position: int) -> str:
    """Return the line about the position: the move number and the move, or the start of the game."""
    move = record.move_at(position)
    if move is None:
        return texts.text("viewer_start", total=record.last_position)
    point = texts.text("viewer_pass") if move.move.is_pass else move.move.gtp()
    color = texts.color_name(move.move.color)
    return texts.text("viewer_move", number=move.number, total=record.last_position, color=color, point=point)


def loss_text(record: GameRecord, position: int) -> str:
    """Return KaTrain's loss and best move for the move of a position ("" if KaTrain wrote no loss)."""
    move = record.move_at(position)
    info = move.katrain if move is not None else None
    if info is None or info.points_lost is None:
        return ""
    return texts.text("viewer_loss", loss=f"{info.points_lost:.1f}", best=info.best_move or "-")


def comment_text(record: GameRecord, position: int) -> str:
    """Return the AI commentary and the user's notes on the move of a position (see texts.notes_text).

    The move that holds the AI review of the whole game (the last move) also shows the
    review, so that "next AI commentary" ends at the review instead of an empty text.
    """
    move = record.move_at(position)
    if move is None or not move.ai_review:
        notes = move.notes if move is not None else ""
        return texts.notes_text(notes, ai_comment=move_commentary(record, position))
    review = f"{texts.text('ai_review')}\n{move.ai_review}"
    if not (move.ai_text or move.notes):
        return review
    return f"{texts.notes_text(move.notes, ai_comment=move.ai_text)}\n\n{review}"


def browse_comment_text(record: GameRecord, browse: Browse, added: Added = NONE_ADDED) -> str:
    """Return the comment shown at where the screen is (see comment_text).

    While the comparison model's sequence is shown, the AI commentary and the AI review are not
    shown (they are another AI's view, as in the quiz): only the user's notes are.
    """
    if not _shows_compare(record, browse, added):
        return comment_text(record, browse.position)
    move = record.move_at(browse.position)
    return texts.notes_text(move.notes if move is not None else "")


def _shows_compare(record: GameRecord, browse: Browse, added: Added) -> bool:
    """True while the comparison model's sequence is shown."""
    if browse.variation is None:
        return False
    return variations_at(record, browse.position, added)[browse.variation].source == SOURCE_COMPARE


def game_label(game: GameFile) -> str:
    """Return the text of a game in the list: its file name, with AI_MARK if it has an AI commentary."""
    return f"{AI_MARK} {game.name}" if game.has_ai else game.name


def variations_at(record: GameRecord, position: int, added: Added = NONE_ADDED) -> tuple[Variation, ...]:
    """Return the sequences that can be shown in place of the move of a position.

    They are KaTrain's predicted sequence (if KaTrain wrote one), the other branches of the
    SGF file at that move, and the comparison model's sequence (if it is in added). Position 0 has none.
    """
    move = record.move_at(position)
    if move is None:
        return ()
    found = []
    info = move.katrain
    if info is not None and info.pv and info.pv_color:
        found.append(Variation(moves_from_gtp(info.pv, info.pv_color), SOURCE_KATRAIN))
    found += [Variation(branch, SOURCE_BRANCH) for branch in move.branches]
    if position in added:
        found.append(added[position])
    return tuple(found)


def go_to(record: GameRecord, position: int) -> Browse:
    """Return a position of the game itself (a number outside the game is moved into it)."""
    return Browse(next_position(record, position, 0))


def step_game(record: GameRecord, browse: Browse, step: int, added: Added = NONE_ADDED) -> Browse:
    """Move some moves through the game (or through the shown sequence, if one is shown)."""
    if browse.variation is None:
        return go_to(record, browse.position + step)
    return step_variation(record, browse, step, added)


def step_variation(record: GameRecord, browse: Browse, step: int, added: Added = NONE_ADDED) -> Browse:
    """Play the shown sequence some moves forward (or back, if step is negative).

    Going back before its first move goes to the game just before the move it replaces
    (the same board). The end of the sequence is as far as it goes.
    """
    variation = variations_at(record, browse.position, added)[browse.variation]
    new_step = min(browse.step + step, len(variation.moves))
    if new_step < 1:
        return go_to(record, browse.position - 1)
    return Browse(browse.position, browse.variation, new_step)


def next_variation(record: GameRecord, browse: Browse, added: Added = NONE_ADDED) -> Browse:
    """Switch between the game and the sequences at the move (Tab).

    From the game, the first sequence is shown with its first move in place of the move of
    the game. From a sequence, the next one is shown in the same way, and after the last one
    the game is shown again at the move where the sequences branch off. Nothing happens
    where there is no sequence.
    """
    variations = variations_at(record, browse.position, added)
    if not variations:
        return browse
    index = 0 if browse.variation is None else browse.variation + 1
    if index >= len(variations):
        return Browse(browse.position)
    return Browse(browse.position, index, 1)


def is_last_sequence(record: GameRecord, browse: Browse, added: Added = NONE_ADDED) -> bool:
    """True when Tab would go back to the game: the last sequence is shown, or the game where there is none."""
    count = len(variations_at(record, browse.position, added))
    return browse.variation == count - 1 if browse.variation is not None else count == 0


def sequence_at_end(record: GameRecord, browse: Browse, added: Added = NONE_ADDED) -> Variation | None:
    """Return the shown sequence when it is shown to its last move (where its territory can be shown), else None."""
    if browse.variation is None:
        return None
    variation = variations_at(record, browse.position, added)[browse.variation]
    return variation if variation.moves and browse.step == len(variation.moves) else None


def browse_view(record: GameRecord, browse: Browse, added: Added = NONE_ADDED) -> BoardView:
    """Return the board: the position of the game, or the sequence played in place of its move.

    In a sequence, its moves are numbered, and the move of the game is marked. In the
    comparison model's sequence, its first move and the last move shown get its own mark.
    """
    if browse.variation is None:
        return board_view(record, browse.position)
    variation = variations_at(record, browse.position, added)[browse.variation]
    move = record.move_at(browse.position)
    found = [(move.move if move is not None else None, MARK_ACTUAL)]
    if variation.source == SOURCE_COMPARE and browse.step >= 1:
        found += [(variation.moves[0], MARK_COMPARE), (variation.moves[browse.step - 1], MARK_COMPARE)]
    marks = collect_marks(found)
    return make_board_view(record.position_before(browse.position), variation.moves[: browse.step], marks)


def variation_text(record: GameRecord, browse: Browse, added: Added = NONE_ADDED) -> str:
    """Return the text about the shown sequence: the order of the sequences, which one, and its moves.

    In the game, it tells whether there are sequences at this move ("" at position 0).
    """
    variations = variations_at(record, browse.position, added)
    if browse.variation is None:
        if record.move_at(browse.position) is None:
            return ""
        return texts.text("viewer_variations" if variations else "viewer_no_variations", count=len(variations))
    variation = variations[browse.variation]
    order = texts.sequence_order_text([(v.source, "") for v in variations], browse.variation)
    shown = texts.sequence_text(
        variation.source, browse.variation + 1, len(variations), browse.step, len(variation.moves)
    )
    moves = _moves_line(variation.moves, browse.step)
    return f"{order}\n{shown}\n{texts.text('viewer_variation_moves', number=browse.position, moves=moves)}"


def _moves_line(moves: tuple[Move, ...], step: int) -> str:
    """Return the moves of a sequence, with the last shown move in brackets (markup is escaped)."""
    names = [texts.text("viewer_pass") if move.is_pass else move.gtp() for move in moves]
    if 1 <= step <= len(names):
        names[step - 1] = f"&bl;{names[step - 1]}&br;"
    return " ".join(names)
