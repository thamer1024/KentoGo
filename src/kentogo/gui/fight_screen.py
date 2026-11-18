"""The screen of the local fight problems: the board on the left, and the information and buttons on the right.

The fights are asked one by one by quiz.fight_quiz; this screen only shows them and passes on the clicks. The
board shows the fight's position (its last move, the opponent's move into the user's area, is marked) and the
moves played since then, numbered. The user plays a move with a click; KataGo answers on the board, and the
user plays again, until the fight is judged (see quiz.fight_judge). The panel tells whose turn it is, while
KataGo reads, and how the fight ended. The next problem can always be asked (Enter): KataGo's answers about the
fight left are not used. The fights are not rotated and their colors are not swapped.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView

from kentogo.gui import texts, theme
from kentogo.gui.board_view import make_board_view
from kentogo.gui.board_widget import BoardWidget
from kentogo.gui.file_name_row import FileNameRow
from kentogo.gui.widgets import fitting_label, flat_button, in_main_thread, set_background, set_text
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_quiz import PHASE_ENDED, PHASE_ERROR, PHASE_STARTING, PHASE_TURN, FightQuiz
from kentogo.quiz.fight_run import FightRun

KEY_ENTERS = (13, 271)  # Kivy's key codes of Enter.
MIN_PANEL_RATIO = 0.3  # The right panel gets at least this part of the screen width.
INFO_HEIGHT = 86  # dp: the kind of the problem in big letters, and the game and the problem on two lines.


class FightScreen(BoxLayout):
    """The screen that asks the local fight problems.

    Attributes:
        quiz: The fights and the one asked now.
    """

    def __init__(
        self,
        fights: list[LocalFight],
        make_run: Callable[[LocalFight], FightRun],
        save: Callable[[FightRun], None],
        on_back: Callable[[], None],
        **kwargs,
    ):
        """Make the screen and ask the first fight.

        Args:
            fights: The fights to ask, in order.
            make_run: Makes the play of a fight against KataGo.
            save: Saves the answer of a fight that has ended.
            on_back: Called by the "back to the top screen" button.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="horizontal", **kwargs)
        self.quiz = FightQuiz(fights, make_run, save, self, in_main_thread)
        self._build(on_back)
        Window.bind(on_key_down=self._on_key_down)
        self.quiz.start(0)

    def _build(self, on_back: Callable[[], None]) -> None:
        """Make the board and the panel."""
        self.board = BoardWidget(size_hint_x=None)
        self.board.bind(on_point=self._on_point)
        self.add_widget(self.board)
        self.bind(size=self._fit_board)

        panel = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        set_background(panel, theme.BOX_BACKGROUND_COLOR)
        self.info_label = fitting_label(dp(INFO_HEIGHT), halign="center")
        self.status_label = fitting_label(dp(112))
        texts_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        texts_box.bind(minimum_height=texts_box.setter("height"))
        texts_box.add_widget(self.info_label)
        texts_box.add_widget(self.status_label)
        texts_scroll = ScrollView(do_scroll_x=False)
        texts_scroll.add_widget(texts_box)

        self.file_row = FileNameRow()
        self._next_button = flat_button(texts.lazy("next_problem"), self.next_fight, size_hint_y=None, height=dp(44))
        back_button = flat_button(texts.lazy("back_to_top"), on_back, size_hint_y=None, height=dp(44))
        for widget in (self.file_row, texts_scroll, self._next_button, back_button):
            panel.add_widget(widget)
        self.add_widget(panel)

    def _fit_board(self, *_args) -> None:
        """Make the board as wide as the screen is tall, but leave at least MIN_PANEL_RATIO for the panel."""
        self.board.width = min(self.height, self.width * (1 - MIN_PANEL_RATIO))

    def changed(self) -> None:
        """Show the fight asked now (the quiz tells it after every change)."""
        quiz = self.quiz
        run = quiz.run
        if run is None:
            self.board.show(None)
            set_text(self.info_label, str)
            set_text(self.status_label, texts.lazy("fights_done"))
            self.file_row.set_name("")
            self._next_button.disabled = True
            return
        fight = run.fight
        self.board.show(make_board_view(fight.position, run.played))
        number, total = quiz.index + 1, len(quiz.fights)
        set_text(self.info_label, lambda: texts.fight_info(fight, number, total))
        self.file_row.set_name(Path(fight.sgf_path).name)
        set_text(self.status_label, self._status())

    def _status(self) -> Callable[[], str]:
        """Return what the panel tells about the phase of the fight asked now."""
        quiz = self.quiz
        if quiz.phase == PHASE_ENDED:
            outcome = quiz.run.outcome
            return lambda: texts.fight_outcome_text(outcome)
        if quiz.phase == PHASE_ERROR:
            return texts.lazy("fight_error", reason=quiz.error)
        if quiz.phase == PHASE_STARTING:
            return texts.lazy("fight_starting")
        if quiz.phase == PHASE_TURN:
            color = quiz.run.color
            return lambda: texts.text("fight_turn", color=texts.color_name(color))
        return texts.lazy("fight_waiting")

    def _on_point(self, _widget, point: tuple[int, int]) -> None:
        """Take a click on the board as the user's move."""
        reason = self.quiz.play(point)
        if reason:
            set_text(self.status_label, texts.lazy("illegal_move", reason=reason))
        # 修正：石が置かれた直後に新しい盤面を描画する
        view = make_board_view(self.quiz.run.fight.position, self.quiz.run.played)
        self.board.show(view)


    def next_fight(self) -> None:
        """Ask the next fight."""
        self.quiz.next_fight()

    def close(self) -> None:
        """Leave the screen: stop using KataGo's answers and listening to the keys."""
        self.quiz.leave()
        Window.unbind(on_key_down=self._on_key_down)

    def _on_key_down(self, _window, key: int, _scancode, _text, _modifiers: list[str]) -> bool:
        """Enter asks the next fight (not while a popup, such as the settings screen, is open)."""
        if any(isinstance(widget, ModalView) for widget in Window.children):
            return False
        if key in KEY_ENTERS:
            self.next_fight()
            return True
        return False


