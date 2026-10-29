"""The progress of one problem: asking, answering, and showing the answer.

A session has two steps for an answer, and it does not use threads:

1. answer() takes the user's move. If the loss of the move is already known
   from the SGF file (the best move, the game move, or a candidate move in
   KaTrain's analysis data), the result is ready.
2. Otherwise the loss is calculated by KataGo later (in another thread), and
   the screen passes it to apply_evaluation() in the main thread. KataGo's
predicted sequences after the answer and after the game move are then added
as more sequences.

After the answer, the sequences are shown in a fixed order (see choices):
KataGo's sequence after the answer, the sequences in the SGF file, the comparison
model's sequence, and KataGo's sequence after the game move. The first one is
shown first. A sequence that KataGo is still calculating (see expect) is in the
order too, without moves, so that the user can see that it is coming.

The comparison model judges the answer too (see apply_compare_evaluation). While
its sequence is shown, its result is shown (see displayed_result); with any other
sequence, the usual result is shown.

The problem can be shown rotated, flipped, or with colors swapped. The user
answers on that board, and the board stays the same after the answer. The
session keeps everything in the original direction and colors, and the
"shown_" properties give them as they are shown. The notes are rewritten to
match the shown board (see notes_transform).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from kentogo.common.board import Board, IllegalMoveError
from kentogo.common.types import Move
from kentogo.mistakes.problem import (
    SOURCE_KATAGO_ACTUAL,
    SOURCE_KATAGO_ANSWER,
    SOURCE_KATAGO_COMPARE,
    Problem,
    Variation,
)
from kentogo.quiz.judge import ScoringPolicy, judge_answer
from kentogo.quiz.notes_transform import transform_notes
from kentogo.quiz.score import Comparison, compare_with_actual
from kentogo.quiz.transform import IDENTITY, BoardTransform

ASKING = "asking"
ANSWERED = "answered"

# The sequences of the game, which the AI commentary of the game talks about.

# The state of a sequence in choices: ready to show, can be calculated when it is chosen
# (see offer), still being calculated, or failed.
READY = ""
OFFERED = "offered"
WAITING = "waiting"
FAILED = "failed"


@dataclass(frozen=True)
class SequenceChoice:
    """One sequence in the order of choices.

    Attributes:
        source: Where the sequence comes from, such as "katrain" or SOURCE_KATAGO_ANSWER.
        variation: The sequence, or None while it is being calculated (or when that failed).
        status: READY, OFFERED, WAITING or FAILED.
    """

    source: str
    variation: Variation | None
    status: str = READY


@dataclass(frozen=True)
class AnswerResult:
    """The result of an answer, in the original direction and colors.

    Attributes:
        answer: The user's move.
        answer_loss: Points lost by the answer, or None if it is not known yet.
        comparison: The answer compared with the game move, or None if the loss is not known yet.
        correct: True or False, or None if the loss is not known yet.
    """

    answer: Move
    answer_loss: float | None
    comparison: Comparison | None
    correct: bool | None


class QuizSession:
    """One problem being asked.

    Attributes:
        problem: The problem in the original direction and colors.
        policy: The rule for deciding whether an answer is correct.
        transform: How the problem is shown (rotated, flipped, colors swapped).
        phase: ASKING before the answer, ANSWERED after it.
        result: The result of the answer, or None before the answer.
        compare_result: The result calculated by the comparison model, or None if there is none.
        compare_best: The comparison model's best move, or None if it is not known.
        compare_best_loss: Points lost by that move (seen by the comparison model), or None.
        replay_step: How many moves of the sequence are shown.
    """

    def __init__(
        self, problem: Problem, policy: ScoringPolicy, transform: BoardTransform = IDENTITY, use_sgf_losses: bool = True
    ):
        """Start asking a problem.

        Args:
            problem: The problem in the original direction and colors.
            policy: The rule for deciding whether an answer is correct.
            transform: How to change the problem while it is asked.
            use_sgf_losses: Use the losses written in the SGF file (KaTrain's model). When another
                model judges the answers, this is False, so that every answer is calculated by that
                model, and both losses come from the same model.
        """
        self.problem = problem
        self.policy = policy
        self.transform = transform
        self.use_sgf_losses = use_sgf_losses
        self.phase = ASKING
        self.result: AnswerResult | None = None
        self.compare_result: AnswerResult | None = None
        self.compare_best: Move | None = None
        self.compare_best_loss: float | None = None
        self.replay_step = 0
        self._added: dict[str, Variation] = {}  # KataGo's sequences, by source.
        self._status: dict[str, str] = {}  # KataGo's sequences that are not there, by source.
        self._selected = 0  # The index of the shown sequence in choices.

    @property
    def shown_problem(self) -> Problem:
        """The problem as it is shown: changed by the transform, before and after the answer.

        Its notes and its AI commentary are rewritten for the shown board.
        """
        shown = self.transform.problem(self.problem)
        size = self.problem.position.size
        return replace(
            shown,
            notes=transform_notes(self.problem.notes, self.transform, size),
            ai_comment=transform_notes(self.problem.ai_comment, self.transform, size),
        )

    @property
    def shown_result(self) -> AnswerResult | None:
        """The result with the answer as it is shown, or None before the answer."""
        if self.result is None:
            return None
        return replace(self.result, answer=self.shown_move(self.result.answer))

    def shown_move(self, move: Move) -> Move:
        """Return a move in the original direction and colors as it is shown."""
        return self.transform.move(move, self.problem.position.size)

    @property
    def notes_visible(self) -> bool:
        """The notes are shown only after the answer."""
        return self.phase == ANSWERED

    def answer(self, shown_move: Move) -> AnswerResult:
        """Take the user's answer.

        Args:
            shown_move: The move on the board as it is shown (changed while asking).

        Returns:
            The result. If the loss is not known yet, answer_loss, comparison and
            correct are None until apply_evaluation() is called.

        Raises:
            RuntimeError: If the problem was already answered.
            IllegalMoveError: If the move has the wrong color or cannot be played.
        """
        if self.phase != ASKING:
            raise RuntimeError("the problem was already answered")
        shown = self.shown_problem.position
        if shown_move.color != shown.next_color:
            raise IllegalMoveError(f"it is {shown.next_color}'s turn")
        if not Board.from_position(shown).is_legal(shown_move):
            raise IllegalMoveError(f"{shown_move.gtp()} cannot be played")

        move = self.transform.inverse().move(shown_move, shown.size)
        self.phase = ANSWERED
        self.result = self._make_result(move, self.known_loss(move), self.problem.points_lost)
        return self.result

    def known_loss(self, move: Move) -> float | None:
        """Return the loss of a move if it is known from the SGF file, or None.

        It is known for the best move, the game move, and the candidate moves in
        KaTrain's analysis data (KT), if the game has it.

        Args:
            move: A move in the original direction and colors.
        """
        if not self.use_sgf_losses:
            return None
        elif self.problem.best_move is not None and move == self.problem.best_move:
            return 0.0
        elif move == self.problem.actual_move:
            return self.problem.points_lost
        else:
            return dict(self.problem.candidate_losses).get(move.gtp())

    def apply_evaluation(
        self,
        answer_loss: float,
        actual_loss: float,
        answer_sequence: tuple[Move, ...] = (),
        actual_sequence: tuple[Move, ...] = (),
    ) -> AnswerResult:
        """Set the losses calculated by KataGo, and judge the answer again.

        Both losses must be calculated under the same conditions, so the loss of
        the game move is also given, instead of the value from the SGF file.
        KataGo's sequences after the answer and after the game move are added with add_sequence().

        Args:
            answer_loss: Points lost by the answer.
            actual_loss: Points lost by the game move.
            answer_sequence: KataGo's predicted moves after the answer.
            actual_sequence: KataGo's predicted moves after the game move.

        Returns:
            The new result.

        Raises:
            RuntimeError: If the problem has not been answered yet.
        """
        if self.result is None:
            raise RuntimeError("the problem has not been answered yet")
        self.result = self._make_result(self.result.answer, answer_loss, actual_loss)
        if answer_sequence:
            self.add_sequence(self.result.answer, answer_sequence, SOURCE_KATAGO_ANSWER)
        else:
            self.fail(SOURCE_KATAGO_ANSWER)
        if actual_sequence:
            self.add_sequence(self.problem.actual_move, actual_sequence, SOURCE_KATAGO_ACTUAL)
        else:
            self.fail(SOURCE_KATAGO_ACTUAL)
        return self.result

    def apply_compare_evaluation(
        self,
        answer_loss: float,
        actual_loss: float,
        best_sequence: tuple[Move, ...],
        best_loss: float | None = None,
    ) -> AnswerResult:
        """Keep the comparison model's losses and add its best sequence (shown when that sequence is chosen).

        Args:
            answer_loss: Points lost by the answer, calculated by the comparison model.
            actual_loss: Points lost by the game move, calculated by the comparison model.
            best_sequence: The comparison model's best sequence in the problem position.
            best_loss: Points lost by the comparison model's best move, or None if not known.

        Returns:
            The comparison model's result.

        Raises:
            RuntimeError: If the problem has not been answered yet.
        """
        if self.result is None:
            raise RuntimeError("the problem has not been answered yet")
        self.compare_result = self._make_result(self.result.answer, answer_loss, actual_loss)
        if best_sequence:
            self.compare_best = best_sequence[0]
            self.compare_best_loss = best_loss
            self.add_sequence(best_sequence[0], best_sequence[1:], SOURCE_KATAGO_COMPARE)
        else:
            self.fail(SOURCE_KATAGO_COMPARE)
        return self.compare_result

    @property
    def showing_compare(self) -> bool:
        """True while the comparison model's sequence is shown and its result is known."""
        choice = self.choice
        return self.compare_result is not None and choice is not None and choice.source == SOURCE_KATAGO_COMPARE

    def sequence_at_end(self) -> Variation | None:
        """Return the shown sequence when it is shown to its last move and it is not the game's continuation.

        The territory and the standing can be shown there (see katago.estimate). None otherwise.
        """
        choice = self.choice
        variation = self.variation
        if self.phase != ANSWERED or choice is None or variation is None or not variation.moves:
            return None
        if choice.source == SOURCE_KATAGO_ACTUAL or self.replay_step != len(variation.moves):
            return None
        return variation

    def sequence_loss(self) -> tuple[Move, float | None] | None:
        """Return the first move of the shown sequence and its loss, when it is not the answer.

        The loss is the game move's (as in the result) for the game move, else the loss known from
        the SGF file (see known_loss; None if it is not known). None while the answer's sequence
        (or none, or the comparison model's sequence with its own result) is shown.
        """
        variation = self.variation
        result = self.result
        if self.phase != ANSWERED or result is None or variation is None or not variation.moves:
            return None
        move = variation.moves[0]
        if move == result.answer or self.showing_compare:
            return None
        if move == self.problem.actual_move and result.comparison is not None:
            return move, result.comparison.actual_loss
        return move, self.known_loss(move)

    @property
    def displayed_result(self) -> AnswerResult | None:
        """The result to show, as it is shown on the board: the comparison model's while its sequence is shown."""
        result = self.compare_result if self.showing_compare else self.result
        if result is None:
            return None
        return replace(result, answer=self.shown_move(result.answer))

    def offer(self, source: str) -> None:
        """Put a sequence in the order that KataGo calculates only when the user chooses it.

        Args:
            source: SOURCE_KATAGO_ANSWER, SOURCE_KATAGO_COMPARE or SOURCE_KATAGO_ACTUAL.
        """
        if source not in self._added and source not in self._status and self._is_needed(source):
            self._status[source] = OFFERED

    def expect(self, source: str) -> None:
        """Tell that KataGo is calculating a sequence, so that it is shown as being calculated.

        Args:
            source: SOURCE_KATAGO_ANSWER, SOURCE_KATAGO_COMPARE or SOURCE_KATAGO_ACTUAL.
        """
        if source not in self._added and self._is_needed(source):
            self._status[source] = WAITING

    def fail(self, source: str) -> None:
        """Tell that KataGo could not calculate a sequence that was expected."""
        if source in self._status:
            self._status[source] = FAILED

    def add_sequence(self, move: Move, sequence: tuple[Move, ...], source: str) -> None:
        """Add a sequence that starts with a move and continues with KataGo's predicted moves.

        The shown sequence stays the same (it is found again in the new order).

        Args:
            move: The first move (the answer, the game move, or the comparison model's best move).
            sequence: The predicted moves after it.
            source: SOURCE_KATAGO_ANSWER, SOURCE_KATAGO_COMPARE or SOURCE_KATAGO_ACTUAL.
        """
        if not self._is_needed(source):
            return
        shown = self.choice
        self._status.pop(source, None)
        self._added[source] = Variation((move, *sequence), source)
        if shown is not None and shown.variation is None and shown.source == source:
            return  # The same place in the order now has the moves.
        if shown is not None:
            self._selected = self._index_of(shown)

    def _is_needed(self, source: str) -> bool:
        """The sequence after the game move is not needed when the answer is the game move."""
        return not (
            source == SOURCE_KATAGO_ACTUAL
            and self.result is not None
            and self.result.answer == self.problem.actual_move
        )

    def _make_result(self, move: Move, answer_loss: float | None, actual_loss: float) -> AnswerResult:
        """Make the result of an answer. If answer_loss is None, the result is not judged yet."""
        if answer_loss is None:
            return AnswerResult(move, None, None, None)
        comparison = compare_with_actual(actual_loss, answer_loss)
        return AnswerResult(move, answer_loss, comparison, judge_answer(actual_loss, answer_loss, self.policy))

    @property
    def choices(self) -> tuple[SequenceChoice, ...]:
        """All sequences to show after the answer, in the order that Tab goes through them.

        KataGo's sequence after the answer, the sequences in the SGF file, KataGo's sequence
        after the game move, and last the comparison model's sequence (another AI). KataGo's
        sequences are there only when they are added, expected or offered.
        """
        sgf = tuple(SequenceChoice(variation.source, variation) for variation in self.problem.variations)
        return (
            *self._katago_choice(SOURCE_KATAGO_ANSWER),
            *sgf,
            *self._katago_choice(SOURCE_KATAGO_ACTUAL),
            *self._katago_choice(SOURCE_KATAGO_COMPARE),
        )

    def _katago_choice(self, source: str) -> tuple[SequenceChoice, ...]:
        """Return KataGo's sequence of a source as a choice (empty if it is neither added nor expected)."""
        if source in self._added:
            return (SequenceChoice(source, self._added[source]),)
        if source in self._status:
            return (SequenceChoice(source, None, self._status[source]),)
        return ()

    def _index_of(self, choice: SequenceChoice) -> int:
        """Return the index of a choice (by its source and moves) in the current order, or 0."""
        for index, other in enumerate(self.choices):
            if other.source == choice.source and (other.variation == choice.variation or choice.variation is None):
                return index
        return 0

    @property
    def variations(self) -> tuple[Variation, ...]:
        """The sequences that can be shown now (with moves), in the order of choices."""
        return tuple(choice.variation for choice in self.choices if choice.variation is not None)

    @property
    def variation_index(self) -> int:
        """The index of the shown sequence in choices."""
        return min(self._selected, max(len(self.choices) - 1, 0))

    @property
    def choice(self) -> SequenceChoice | None:
        """The sequence that is shown (or is being calculated), or None if there is none."""
        choices = self.choices
        return choices[self.variation_index] if choices else None

    @property
    def shows_ai_comment(self) -> bool:
        """True while the AI commentary of the move is shown: with every sequence but the comparison model's.

        The comparison model's sequence is another AI's view, so the commentary is not shown with it.
        """
        choice = self.choice
        return choice is None or choice.source != SOURCE_KATAGO_COMPARE

    @property
    def shows_verdict(self) -> bool:
        """True while the result of the answer (correct or wrong) is shown: with the answer's own sequence.

        Without KataGo there is no sequence after the answer, so the result is shown with the first
        sequence instead (the one shown right after answering).
        """
        choice = self.choice
        if choice is None or choice.source == SOURCE_KATAGO_ANSWER:
            return True
        katago_answer = SOURCE_KATAGO_ANSWER in self._added or SOURCE_KATAGO_ANSWER in self._status
        return not katago_answer and self.variation_index == 0

    @property
    def variation(self) -> Variation | None:
        """The moves of the shown sequence, or None if there is none or it is being calculated."""
        choice = self.choice
        return choice.variation if choice is not None else None

    def select_variation(self, index: int) -> None:
        """Choose another sequence (an index of choices), and show it from the start.

        Raises:
            IndexError: If there is no sequence with that index.
        """
        if not 0 <= index < len(self.choices):
            raise IndexError(f"no sequence {index}")
        self._selected = index
        self.replay_step = 0

    def next_variation(self) -> None:
        """Choose the next sequence (after the last one, the first one), and show it from the start."""
        if self.choices:
            self.select_variation((self.variation_index + 1) % len(self.choices))

    def step_forward(self) -> None:
        """Show one more move of the sequence (nothing happens before the answer or at the end)."""
        if self.phase == ANSWERED and self.variation is not None and self.replay_step < len(self.variation.moves):
            self.replay_step += 1

    def step_back(self) -> None:
        """Show one move less of the sequence (nothing happens at the start)."""
        if self.replay_step > 0:
            self.replay_step -= 1

    def shown_sequence(self) -> tuple[Move, ...]:
        """Return the moves of the sequence that are shown now, on top of the shown problem position."""
        if self.phase != ANSWERED or self.variation is None:
            return ()
        return self.transform.moves(self.variation.moves[: self.replay_step], self.problem.position.size)
