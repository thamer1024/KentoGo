"""The report screen (成績表): the numbers of all the practice, the latest practice days, and two charts.

The numbers come from kentogo.report (made in a background thread by the app). The charts are
plain bars drawn on the canvas, the oldest on the left: one for each practice day (the part of
correct answers and the average part got back, with the pass ratio as a line), and one for each
game (its big mistakes, stacked). Only the latest SHOWN days and games are drawn.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from kentogo.gui import texts, theme
from kentogo.gui.widgets import flat_button, growing_label, set_background, set_text, wrapping_label
from kentogo.report import RECENT, Report

SHOWN = 20  # The most days (or games) drawn in a chart.
CHART_HEIGHT = 160  # dp
CORRECT_COLOR = (0.35, 0.6, 0.95, 1)  # The part of correct answers.
AVERAGE_COLOR = (0.4, 0.8, 0.5, 1)  # The average part got back.
BIG_COLOR = (0.9, 0.35, 0.35, 1)  # Mistakes of 20 points or more.
LARGE_COLOR = (0.95, 0.65, 0.3, 1)  # Mistakes of 10 to 20 points.
LINE_COLOR = (0.95, 0.95, 0.95, 0.8)  # The pass ratio, and the bottom line.
GRID_COLOR = (1, 1, 1, 0.12)


class BarChart(Widget):
    """Bars in groups, side by side or stacked, with an optional level line.

    Each group is drawn in a slot of the same width; inside a group, each value has its own color.
    """

    def __init__(
        self,
        groups: Sequence[Sequence[float]],
        colors: Sequence[tuple],
        top: float,
        stacked: bool = False,
        level: float | None = None,
        **kwargs,
    ):
        """Make the chart.

        Args:
            groups: The values of each group, the oldest first.
            colors: The color of each value of a group.
            top: The value at the top of the chart.
            stacked: Stack the values of a group (else they are side by side).
            level: A value drawn as a line across the chart, or None.
            **kwargs: Kivy's widget arguments.
        """
        super().__init__(size_hint_y=None, height=dp(CHART_HEIGHT), **kwargs)
        self.groups, self.colors, self.top_value = list(groups), list(colors), max(top, 1e-9)
        self.stacked, self.level = stacked, level
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

    def redraw(self) -> None:
        """Draw the bars again for the size and the place of the widget."""
        self.canvas.clear()
        with self.canvas:
            Color(*GRID_COLOR)
            Rectangle(pos=self.pos, size=self.size)
            if self.groups:
                self._draw_bars()
            Color(*LINE_COLOR)
            Line(points=[self.x, self.y, self.right, self.y], width=1)
            if self.level is not None:
                y = self.y + self.height * min(self.level / self.top_value, 1.0)
                Line(points=[self.x, y, self.right, y], width=1, dash_length=6, dash_offset=4)

    def _draw_bars(self) -> None:
        """Draw each group in its slot."""
        slot = self.width / max(len(self.groups), RECENT)
        count = len(self.colors)
        bar = slot * 0.8 if self.stacked else slot * 0.8 / count
        for index, values in enumerate(self.groups):
            left = self.x + index * slot + slot * 0.1
            bottom = self.y
            for value_index, value in enumerate(values):
                height = self.height * min(value / self.top_value, 1.0)
                x = left if self.stacked else left + value_index * bar
                Color(*self.colors[value_index])
                Rectangle(pos=(x, bottom), size=(bar, height))
                if self.stacked:
                    bottom += height


class ReportScreen(BoxLayout):
    """The report screen."""

    def __init__(self, report: Report, on_back: Callable[[], None], **kwargs):
        """Make the screen.

        Args:
            report: The numbers to show (see kentogo.report).
            on_back: Called by the back button.
            **kwargs: Kivy's layout arguments.
        """
        super().__init__(orientation="vertical", padding=dp(16), spacing=dp(8), **kwargs)
        title = wrapping_label(halign="center", valign="middle", font_size=sp(26), size_hint_y=None, height=dp(48))
        set_text(title, texts.lazy("report_title"))
        self.add_widget(title)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(_content(report))
        self.add_widget(scroll)
        self.add_widget(flat_button(texts.lazy("back_to_top"), on_back, size_hint_y=None, height=dp(48)))


def _content(report: Report) -> BoxLayout:
    """Make the column with the numbers and the charts."""
    box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(16), spacing=dp(12))
    box.bind(minimum_height=box.setter("height"))
    set_background(box, theme.BOX_BACKGROUND_COLOR)
    box.add_widget(_label(lambda: texts.totals_text(report.totals)))
    box.add_widget(_label(lambda: texts.recent_text(report.recent)))
    box.add_widget(_label(lambda: texts.text("report_days_title", ratio=round(100 * report.pass_ratio))))
    days = report.days[-SHOWN:]
    box.add_widget(
        BarChart(
            [(day.correct / day.answered, day.average or 0.0) for day in days],
            [CORRECT_COLOR, AVERAGE_COLOR],
            1.0,
            level=report.pass_ratio,
        )
    )
    box.add_widget(_label(lambda: texts.text("report_chart_note", count=SHOWN)))
    box.add_widget(_label(lambda: texts.text("report_games_title")))
    games = report.games[-SHOWN:]
    top = max([game.big + game.large for game in games] + [4])
    box.add_widget(BarChart([(game.big, game.large) for game in games], [BIG_COLOR, LARGE_COLOR], top, stacked=True))
    box.add_widget(_label(lambda: texts.game_averages_text(report.game_averages)))
    return box


def _label(make: Callable[[], str]):
    """Make a label that grows with its text, and follows the language."""
    label = growing_label()
    set_text(label, make)
    return label
