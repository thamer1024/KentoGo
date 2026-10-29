"""The quiz screen: the board on the left, and the information and buttons on the right.

The screen shows the problems that quiz.quiz_run asks, one by one, and passes the user's
actions on to it: a click on a point is the answer, and the buttons and keys switch and play
the sequences. What is asked, how answers are judged and saved, and which sequences KataGo
calculates are decided there; this module only shows them.

A rotated or color-swapped board stays the same after the answer, and the moves and the notes
are shown for that board. Tab (or the switch button) goes through the sequences in a fixed order:
KataGo's sequence after the answer (shown first), the sequences in the SGF file, the comparison
model's sequence, and KataGo's sequence after the game move. A line shows this order with the
shown one marked, and which sequences KataGo is still calculating. While KataGo is judging the
answer, the buttons and keys that switch, play back, play forward and go to the next problem
cannot be used (the buttons are drawn as disabled); going to the next problem waits until all
calculations of the problem have arrived, so that KataGo's work does not pile up.
Keys: Space and the right arrow play the sequence forward, Shift+Space and the left arrow play
it back, Tab switches to the next sequence, T shows the territory and the standing, and Enter
goes to the next problem. The settings are changed from the top screen. The panel shows how
many times the problem was asked before and the last result.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView

from kentogo.answers import save_answer
from kentogo.common.types import Move
from kentogo.gui import texts, theme
from kentogo.gui.board_view import (
    MARK_ACTUAL,
    MARK_ANSWER,
    MARK_BEST,
    MARK_COMPARE,
    BoardView,
    collect_marks,
    make_board_view,
)
from kentogo.gui.board_widget import BoardWidget
from kentogo.gui.dialogs import show_message
from kentogo.gui.file_name_row import FileNameRow
from kentogo.gui.widgets import fitting_label, flat_button, growing_label, in_main_thread, set_background, set_text
from kentogo.mistakes.problem import SOURCE_KATAGO_COMPARE, Problem
from kentogo.quiz.judge import ScoringPolicy
from kentogo.quiz.quiz_run import Judging, QuizRun
from kentogo.quiz.session import ANSWERED, QuizSession
from kentogo.quiz.standings import SequenceStandings
from kentogo.quiz.transform import BoardTransform
from kentogo.review.history import AnswerHistory

# Key codes of Kivy.
KEY_LEFT = 276
KEY_RIGHT = 275
KEY_SPACE = 32
KEY_TAB = 9
KEY_T = 116
KEY_ENTERS = (13, 271)

# The right panel gets at least this part of the screen width.
MIN_PANEL_RATIO = 0.3
# The lowest height of the information (dp): the game and the problem on two lines, and one empty line.
INFO_HEIGHT = 58


class QuizScreen(BoxLayout):
    """The screen that shows the problems of a quiz (see quiz.quiz_run).

    Attributes:
        run: The quiz: the problems, the one asked now, and the judging of the answers.
        judging: KataGo for judging the answers and for the territory and the standing.
        history: Where the answers are saved, or None if they are not saved.
        standings: The territory and the standing (T) of the problem asked now, or None after the last one.
    """

    def __init__(
        self,
        problems: list[Problem],
        policy: ScoringPolicy,
        choose_transform: Callable[[], BoardTransform],
        judging: Judging = Judging(),
        start_message: str = "",
        history: AnswerHistory | None = None,
        on_back: Callable[[], None] | None = None,
        open_game: Callable[[Problem], None] | None = None,
        **kwargs,
    ):
        """Make the screen and show the first problem.

        Args:
            problems: The problems to ask, in order.
            policy: The rule for deciding whether an answer is correct.
            choose_transform: A function that returns how to change each problem.
            judging: KataGo for judging the answers (see quiz.quiz_run.Judging).
            start_message: Shown instead of the usual message when there are no problems,
                for example when the games folder is not set.
            history: Where the answers are saved. If None, they are not saved.
            on_back: Called by the "back to the top screen" button; without it, there is no button.
            open_game: Shows the game of a problem at the mistake (after the answer); without it, there is no button.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="horizontal", **kwargs)
        self.judging = judging
        self.start_message = start_message
        self.history = history
        self.on_back = on_back
        self.open_game = open_game
        self.standings: SequenceStandings | None = None
        self._history_line: Callable[[], str] = str  # Makes the line about the earlier answers ("" if none).
        self._busy_since: float | None = None  # When KataGo started calculating for the current problem.
        self._busy_timer = None  # Shows the seconds while KataGo is calculating (see _update_buttons).
        self._shown_errors: set[str] = set()  # Errors already shown in a dialog (each one is shown once).
        self.run = QuizRun(
            problems,
            policy,
            choose_transform,
            judging,
            self,
            save=self._save,
            in_main=in_main_thread,
        )
        self._build()
        Window.bind(on_key_down=self._on_key_down)
        self.run.start(0)

    def _build(self) -> None:
        """Make the widgets of the screen."""
        # The board is square, so that the space around it is the same on every side.
        self.board = BoardWidget(size_hint_x=None)
        self.board.bind(on_point=self._on_point)
        self.add_widget(self.board)
        self.bind(size=self._fit_board)

        panel = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        set_background(panel, theme.BOX_BACKGROUND_COLOR)
        # The texts wrap at the width of the panel and grow taller in a narrow window. They are all
        # in one scroll view, so that every text can be read even when the window is small.
        self.info_label = fitting_label(dp(INFO_HEIGHT), halign="center")
        self.result_label = fitting_label(dp(156))
        self.sequence_label = fitting_label(dp(112))
        self.notes_label = growing_label()
        texts_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        texts_box.bind(minimum_height=texts_box.setter("height"))
        for label in (self.info_label, self.result_label, self.sequence_label, self.notes_label):
            texts_box.add_widget(label)
        texts_scroll = ScrollView(do_scroll_x=False)
        texts_scroll.add_widget(texts_box)

        switch_button = flat_button(texts.lazy("switch_sequence"), self.next_variation)
        switch_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        switch_row.add_widget(switch_button)
        switch_row.add_widget(flat_button(texts.lazy("estimate_button"), self.toggle_standing))
        back_button = flat_button(texts.lazy("back"), self.step_back)
        forward_button = flat_button(texts.lazy("forward"), self.step_forward)
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        buttons.add_widget(back_button)
        buttons.add_widget(forward_button)
        next_button = flat_button(texts.lazy("next_problem"), self.next_problem, size_hint_y=None, height=dp(44))
        # These cannot be used while KataGo is calculating (see _update_buttons).
        self._busy_buttons = (switch_button, back_button, forward_button)
        self._next_button = next_button  # It cannot be used until all calculations have finished.

        self.file_row = FileNameRow()
        for widget in (self.file_row, texts_scroll, switch_row, buttons, next_button):
            panel.add_widget(widget)
        self._open_game_button = None
        if self.open_game is not None:
            self._open_game_button = flat_button(
                texts.lazy("open_game"), self._show_game, size_hint_y=None, height=dp(44)
            )
            panel.add_widget(self._open_game_button)
        if self.on_back is not None:
            panel.add_widget(flat_button(texts.lazy("back_to_top"), self.on_back, size_hint_y=None, height=dp(44)))
        self.add_widget(panel)

    def _fit_board(self, *_args) -> None:
        """Make the board as wide as the screen is tall, but leave at least MIN_PANEL_RATIO for the panel."""
        self.board.width = min(self.height, self.width * (1 - MIN_PANEL_RATIO))

    @property
    def session(self) -> QuizSession | None:
        """The session of the problem asked now, or None after the last problem."""
        return self.run.session

    def start(self, index: int) -> None:
        """Ask the problem with the given index (or show the end message)."""
        self.run.start(index)

    def started(self, session: QuizSession | None) -> None:
        """Show a new problem, or the end message (told by the quiz)."""
        if session is None:
            self.standings = None
            self._show_end()
            return
        self.standings = SequenceStandings(session, in_main_thread)
        self._history_line = self._history_line_of(session.problem)
        self._show_history_error()
        color = session.shown_problem.position.next_color
        set_text(self.result_label, lambda: texts.text("asking", color=texts.color_name(color)))
        self._refresh()

    def changed(self, session: QuizSession) -> None:
        """Show a new result or sequence, if its problem is the one shown now (told by the quiz)."""
        if session is self.session:
            self._show_result(session)
            self._refresh()

    def failed(self, text_key: str, reason: str) -> None:
        """Tell that KataGo could not calculate something, once for each different error (told by the quiz)."""
        self._show_error_once(texts.text(text_key, reason=reason))

    def _show_end(self) -> None:
        """Show the end message (or why there are no problems), with nothing to play."""
        start_message, empty = self.start_message, not self.run.problems
        message = (lambda: start_message or texts.text("no_problems")) if empty else texts.lazy("finished")
        self.board.show(None)
        set_text(self.info_label, message)
        for label in (self.result_label, self.sequence_label, self.notes_label):
            set_text(label, str)
        self._update_buttons()

    def _history_line_of(self, problem: Problem) -> Callable[[], str]:
        """Return what makes the line about the earlier answers to a problem ("" without a history)."""
        if self.history is None:
            return str
        previous = self.history.previous(problem.problem_id)
        return lambda: texts.history_text(previous)

    @property
    def busy(self) -> bool:
        """True while KataGo is judging the answer of the current problem (the buttons cannot be used)."""
        return self.run.busy

    @property
    def calculating(self) -> bool:
        """True while KataGo is judging the answer or calculating a sequence of the current problem."""
        return self.run.calculating

    def next_problem(self) -> None:
        """Go to the next problem (not while KataGo is calculating for this one)."""
        self.run.next_problem()

    def step_back(self) -> None:
        """Show one move less of the sequence (not while KataGo is calculating)."""
        if self.run.can_play():
            self.session.step_back()
            self._sequence_moved()

    def step_forward(self) -> None:
        """Show one more move of the sequence (not while KataGo is calculating)."""
        if self.run.can_play():
            self.session.step_forward()
            self._sequence_moved()

    def _sequence_moved(self) -> None:
        """Hide the territory (it belongs to the end of a sequence) and show the board again."""
        self.standings.hide()
        self._refresh()

    def next_variation(self) -> None:
        """Switch to the next sequence (only after the answer, and not while KataGo is calculating)."""
        if self.run.next_variation():
            self.standings.hide()
            self._show_result(self.session)  # The comparison model's sequence has its own result.
            self._refresh()

    def toggle_standing(self) -> None:
        """Show or hide the territory and the standing at the end of the shown sequence (T, see quiz.standings)."""
        session, standings = self.session, self.standings
        if session is None or standings is None:
            return

        def changed() -> None:
            if session is self.session:
                self._refresh()

        def failed(text_key: str, reason: str) -> None:
            show_message(texts.text("mode_quiz"), texts.text(text_key, reason=reason))

        standings.toggle(self.judging.models(), changed, failed)

    def _on_point(self, _widget, point: tuple[int, int]) -> None:
        """Take a click on the board as the answer."""
        reason = self.run.answer(point)
        if reason:
            set_text(self.result_label, lambda: texts.text("illegal_move", reason=reason))
            return
        session = self.session
        if session is not None and session.phase == ANSWERED:
            self._show_result(session)
            self._refresh()

    def close(self) -> None:
        """Leave the screen: save the answers KataGo is still judging, and stop listening to the keys."""
        self.save_unfinished()
        Window.unbind(on_key_down=self._on_key_down)

    def save_unfinished(self) -> None:
        """Save the answers that KataGo is still judging, without losses (called when the app closes)."""
        self.run.save_unfinished()

    def _save(self, session: QuizSession, max_visits: int | None, comparison_model: bool) -> None:
        """Save an answer to the history (the quiz calls it once for each answer), if there is a history."""
        if self.history is not None:
            save_answer(self.history, session, max_visits, comparison_model)
            self._show_history_error()

    def _show_history_error(self) -> None:
        """Show a dialog if the history could not be read or written (once for each error)."""
        if self.history is not None and self.history.last_error:
            self._show_error_once(texts.text("notice_history_error", reason=self.history.last_error))

    def _show_error_once(self, message: str) -> None:
        """Show an error in a dialog where it can be copied, unless the same error was shown before.

        So the same error does not stop the user at every problem.
        """
        if message not in self._shown_errors:
            self._shown_errors.add(message)
            show_message(texts.text("error_title"), message)

    def _show_result(self, session: QuizSession) -> None:
        """Show the result of the answer, with the moves as they are on the shown board.

        Until KataGo has judged the answer, the reason is shown (see QuizRun.waiting_reason). While
        the comparison model's sequence is shown, its result is shown instead. While another
        sequence is shown, the line of the losses tells about its first move (see QuizSession.sequence_loss).
        """
        reason = self.run.waiting_reason(session)
        waiting = texts.lazy(reason[0], **reason[1]) if reason is not None else str
        problem, result = session.shown_problem, session.displayed_result
        compare_best = session.shown_move(session.compare_best) if session.compare_best else None
        by_compare, compare_loss = session.showing_compare, session.compare_best_loss
        found = session.sequence_loss()
        sequence = (session.shown_move(found[0]), found[1]) if found is not None else None
        set_text(
            self.result_label,
            lambda: texts.result_text(
                problem,
                result,
                waiting(),
                compare_best=compare_best,
                by_compare=by_compare,
                compare_best_loss=compare_loss,
                sequence=sequence,
                show_verdict=session.shows_verdict,
            ),
        )

    def _on_key_down(self, _window, key: int, _scancode, _text, modifiers: list[str]) -> bool:
        """Handle the keys.

        Space or the right arrow plays the sequence forward, Shift+Space or the left
        arrow plays it back, Tab switches the sequence, and Enter goes to the next problem.
        The keys are not used while a popup (such as the settings screen) is open.
        """
        if any(isinstance(widget, ModalView) for widget in Window.children):
            return False
        shift = "shift" in modifiers
        if key == KEY_LEFT or (key == KEY_SPACE and shift):
            self.step_back()
        elif key == KEY_RIGHT or key == KEY_SPACE:
            self.step_forward()
        elif key == KEY_TAB:
            self.next_variation()
        elif key == KEY_T:
            self.toggle_standing()
        elif key in KEY_ENTERS:
            self.next_problem()
        else:
            return False
        return True

    def _refresh(self) -> None:
        """Update the board, the information, the sequence and the notes."""
        session = self.session
        problem = session.shown_problem
        self._update_buttons()
        self.board.show(self._board_view())
        number, total, history_line = self.run.index + 1, len(self.run.problems), self._history_line
        set_text(self.info_label, lambda: _on_one_line(texts.problem_info(problem, number, total), history_line()))
        self.file_row.set_name(Path(problem.sgf_path).name)
        if session.phase != ANSWERED:
            set_text(self.sequence_label, str)
            set_text(self.notes_label, str)
            return
        set_text(self.sequence_label, lambda: self._sequence_text(session))
        # The AI commentary is not shown with the comparison model's sequence (another AI's view).
        ai_comment = problem.ai_comment if session.shows_ai_comment else ""
        set_text(
            self.notes_label,
            lambda: texts.notes_text(problem.notes, ai_comment=ai_comment),
        )

    def _update_buttons(self) -> None:
        """Make the buttons unusable while KataGo judges the answer, and usable again when the result is shown.

        The next problem button waits until all calculations of this problem have finished.

        While KataGo is calculating (the result or a sequence), a timer shows the seconds every
        second, and checks again whether it has finished, so that the buttons come back even if
        an update was missed.
        """
        ended = self.session is None
        busy = self.busy
        for button in self._busy_buttons:
            button.disabled = busy or ended  # After the last problem there is nothing to show.
        if self._open_game_button is not None:
            # Only after the answer: the game shows the move that was played and the best move.
            self._open_game_button.disabled = ended or self.session.phase != ANSWERED
        calculating = self.calculating
        self._next_button.disabled = calculating or ended
        if calculating and self._busy_timer is None:
            self._busy_since = time.monotonic()
            self._busy_timer = Clock.schedule_interval(self._on_busy_timer, 1)
        elif not calculating and self._busy_timer is not None:
            self._busy_timer.cancel()
            self._busy_timer = self._busy_since = None

    def _show_game(self) -> None:
        """Show the game of the current problem at the mistake (after the answer)."""
        if self.session is not None and self.session.phase == ANSWERED and self.open_game is not None:
            self.open_game(self.session.problem)

    def _on_busy_timer(self, _dt) -> None:
        """Show the seconds of calculation, and make the buttons usable when KataGo has finished."""
        if self.session is not None and self.session.phase == ANSWERED:
            session = self.session
            set_text(self.sequence_label, lambda: self._sequence_text(session))
        self._update_buttons()

    @property
    def busy_seconds(self) -> int:
        """How many seconds KataGo has been calculating for the current problem (0 if it is not)."""
        return int(time.monotonic() - self._busy_since) if self._busy_since is not None else 0

    def _sequence_text(self, session: QuizSession) -> str:
        """Return the text about the shown sequence, with the line that shows the order for Tab."""
        choice = session.choice
        if choice is None:
            return texts.text("no_sequence")
        moves = choice.variation.moves if choice.variation is not None else ()
        shown = texts.sequence_text(
            choice.source,
            index=session.variation_index + 1,
            count=len(session.choices),
            step=session.replay_step,
            total=len(moves),
            status=choice.status,
        )
        order = texts.sequence_order_text(
            [(c.source, c.status) for c in session.choices], session.variation_index, self.busy_seconds
        )
        lines = [order, shown]
        standings = self.standings
        if standings is not None and standings.busy:
            lines.append(texts.text("estimate_running"))
        standing = standings.shown() if standings is not None else None
        if standing is not None:
            lines.append(texts.standing_text(standing, session.replay_step))
        return "\n".join(lines)

    def _board_view(self) -> BoardView:
        """Make the view of the board for the current state of the session."""
        session = self.session
        problem = session.shown_problem
        marks = {}
        if session.phase == ANSWERED:
            compare_best = session.shown_move(session.compare_best) if session.compare_best else None
            # Moves on the same point get rings inside each other, in this order from the outside.
            marks = collect_marks(
                [
                    (session.shown_result.answer, MARK_ANSWER),
                    (problem.actual_move, MARK_ACTUAL),
                    (problem.best_move, MARK_BEST),
                    (compare_best, MARK_COMPARE),
                    *_compare_marks(session),
                ]
            )
        view = make_board_view(problem.position, session.shown_sequence(), marks)
        standing = self.standings.shown() if self.standings is not None else None
        return replace(view, ownership=standing.end.ownership) if standing is not None else view


def _compare_marks(session: QuizSession) -> list[tuple[Move, str]]:
    """Return the marks of the comparison model's sequence while it is shown: its first and last shown moves."""
    choice = session.choice
    shown = session.shown_sequence()
    if choice is None or choice.source != SOURCE_KATAGO_COMPARE or not shown:
        return []
    return [(shown[0], MARK_COMPARE), (shown[-1], MARK_COMPARE)]


def _on_one_line(first: str, second: str) -> str:
    """Put a second text at the end of the first one's last line, or return the first alone if the second is ""."""
    return f"{first}{texts.gap()}{second}" if second else first
