"""The report screen (成績表): the numbers of all the practice, the latest practice days, and two charts.

The numbers come from kentogo.report (made in a background thread by the app). The charts are
plain bars drawn on the canvas, the oldest on the left: one for each practice day (the part of
correct answers and the average part got back, with the pass ratio as a dotted line), and one for
each game (its mistakes, stacked by the points lost). Each bar has its value written above it (also 0, so that a
day or a game with nothing to draw is not mistaken for a gap), and each group has its day (and
the number of problems, or the time of the game) written below it. A legend with the colors is
above each chart. Only the latest SHOWN days and games are drawn.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from kentogo.gui import texts, theme
from kentogo.gui.widgets import flat_button, growing_label, set_background, set_text, wrapping_label
from kentogo.report import RECENT, Report, first_bands

SHOWN = 20  # The most days (or games) drawn in a chart.
CHART_BANDS = 3  # Only the biggest bands of mistakes are drawn, so that the many small ones do not hide them.
CHART_HEIGHT = 220  # dp, with the texts above and below the bars.
TOP_SPACE = 18  # dp above the bars, for the values.
BOTTOM_SPACE = 34  # dp below the bars, for two lines about each group.
TEXT_SIZE = 11  # sp
CORRECT_COLOR = (0.35, 0.6, 0.95, 1)  # The part of correct answers.
AVERAGE_COLOR = (0.4, 0.8, 0.5, 1)  # The average part got back.
# The colors of the bands of mistakes, the biggest first (red, orange, yellow, light yellow, then grays).
BAND_COLORS = (
    (0.9, 0.3, 0.3, 1),
    (0.95, 0.6, 0.25, 1),
    (0.95, 0.85, 0.3, 1),
    (0.95, 0.95, 0.7, 1),
    (0.7, 0.7, 0.7, 1),
    (0.5, 0.5, 0.5, 1),
)
LINE_COLOR = (0.95, 0.95, 0.95, 0.8)  # The pass ratio, and the bottom line.
GRID_COLOR = (1, 1, 1, 0.12)


class BarChart(Widget):
    """Bars in groups, side by side or stacked, with their values above and two lines of text below.

    Each group is drawn in a slot of the same width; inside a group, each value has its own color.
    """

    def __init__(
        self,
        groups: Sequence[Sequence[float]],
        colors: Sequence[tuple],
        top: float,
        values_above: Sequence[Sequence[str]],
        texts_below: Sequence[tuple[str, str]],
        stacked: bool = False,
        level: float | None = None,
        **kwargs,
    ):
        """Make the chart.

        Args:
            groups: The values of each group, the oldest first.
            colors: The color of each value of a group.
            top: The value at the top of the chart.
            values_above: The texts written above each group: one for each bar (side by side), or
                one for the whole group (stacked).
            texts_below: Two lines written below each group (such as the day and the number of problems).
            stacked: Stack the values of a group (else they are side by side).
            level: A value drawn as a dotted line across the chart, or None.
            **kwargs: Kivy's widget arguments.
        """
        super().__init__(size_hint_y=None, height=dp(CHART_HEIGHT), **kwargs)
        self.groups, self.colors, self.top_value = list(groups), list(colors), max(top, 1e-9)
        self.values_above, self.texts_below = list(values_above), list(texts_below)
        self.stacked, self.level = stacked, level
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

    def redraw(self) -> None:
        """Draw the bars and the texts again for the size and the place of the widget."""
        self.canvas.clear()
        bottom, height = self.y + dp(BOTTOM_SPACE), self.height - dp(BOTTOM_SPACE) - dp(TOP_SPACE)
        with self.canvas:
            Color(*GRID_COLOR)
            Rectangle(pos=(self.x, bottom), size=(self.width, height))
            slot = self.width / max(len(self.groups), RECENT)
            for index, values in enumerate(self.groups):
                self._draw_group(self.x + index * slot, slot, bottom, height, index, values)
            Color(*LINE_COLOR)
            Line(points=[self.x, bottom, self.right, bottom], width=1)
            if self.level is not None:
                y = bottom + height * min(self.level / self.top_value, 1.0)
                Line(points=[self.x, y, self.right, y], width=1, dash_length=6, dash_offset=4)

    def _draw_group(self, left: float, slot: float, bottom: float, height: float, index: int, values) -> None:
        """Draw the bars of one group, their values above, and its two lines below."""
        count = 1 if self.stacked else len(values)
        bar = slot * 0.8 / count
        base = bottom
        tops = []
        for value_index, value in enumerate(values):
            bar_height = height * min(value / self.top_value, 1.0)
            x = left + slot * 0.1 + (0 if self.stacked else value_index * bar)
            Color(*self.colors[value_index])
            Rectangle(pos=(x, base), size=(bar, bar_height))
            tops.append((x, base + bar_height))
            if self.stacked:
                base += bar_height
        above = self.values_above[index]
        places = [tops[-1]] if self.stacked else tops
        for (x, y), label in zip(places, above, strict=False):
            _draw_text(label, x + bar / 2, y + dp(2), anchor_bottom=True)
        first, second = self.texts_below[index]
        _draw_text(first, left + slot / 2, bottom - dp(3), anchor_bottom=False)
        _draw_text(second, left + slot / 2, bottom - dp(18), anchor_bottom=False)


def _draw_text(text: str, center_x: float, y: float, anchor_bottom: bool) -> None:
    """Draw a short text centered at center_x: its bottom at y (anchor_bottom), or else its top at y."""
    if not text:
        return
    label = CoreLabel(text=text, font_size=sp(TEXT_SIZE), color=theme.TEXT_COLOR)
    label.refresh()
    texture = label.texture
    bottom = y if anchor_bottom else y - texture.height
    Color(1, 1, 1, 1)
    Rectangle(texture=texture, pos=(center_x - texture.width / 2, bottom), size=texture.size)


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
    box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(16), spacing=dp(10))
    box.bind(minimum_height=box.setter("height"))
    set_background(box, theme.BOX_BACKGROUND_COLOR)
    box.add_widget(_label(lambda: texts.totals_text(report.totals)))
    box.add_widget(_label(lambda: texts.recent_text(report.recent)))
    for widget in _days_part(report) + _games_part(report):
        box.add_widget(widget)
    return box


def _days_part(report: Report) -> list[Widget]:
    """Make the title, the legend, the chart and the note of the practice days."""
    days = report.days[-SHOWN:]
    chart = BarChart(
        [(day.correct / day.answered, day.average or 0.0) for day in days],
        [CORRECT_COLOR, AVERAGE_COLOR],
        1.0,
        [(_percent(day.correct / day.answered), _percent(day.average)) for day in days],
        [(f"{day.day.month}/{day.day.day}", texts.text("report_day_count", count=day.answered)) for day in days],
        level=report.pass_ratio,
    )
    legend = _legend(
        [
            (CORRECT_COLOR, "legend_correct", {}),
            (AVERAGE_COLOR, "legend_average", {}),
            (LINE_COLOR, "legend_pass", {"ratio": round(100 * report.pass_ratio)}),
        ]
    )
    return [
        _label(texts.lazy("report_days_title")),
        legend,
        chart,
        _label(texts.lazy("report_chart_note", count=SHOWN)),
    ]


def _games_part(report: Report) -> list[Widget]:
    """Make the title, the legend, the chart and the notes of the games."""
    games = report.games[-SHOWN:]
    bands = report.bands[:CHART_BANDS]
    counts = [game.counts[: len(bands)] for game in games]
    colors = [band_color(index) for index in range(len(bands))]
    top = max([sum(row) for row in counts] + [4])
    chart = BarChart(
        counts,
        colors,
        top,
        [(str(sum(row)),) for row in counts],
        [(f"{game.played.month}/{game.played.day}", game.played.strftime("%H:%M")) for game in games],
        stacked=True,
    )
    legend = _legend([(color, *texts.band_key(bands, index)) for index, color in enumerate(colors)])
    averages = first_bands(report.game_averages, len(bands))
    return [
        _label(texts.lazy("report_games_title", low=texts.points(bands[-1]) if bands else "")),
        legend,
        chart,
        _label(texts.lazy("report_games_note", count=SHOWN)),
        _label(lambda: texts.game_averages_text(averages, bands)),
    ]


def band_color(index: int) -> tuple:
    """Return the color of a band of mistakes (0: the biggest); bands after the last color use the last one."""
    return BAND_COLORS[min(index, len(BAND_COLORS) - 1)]


def _percent(value: float | None) -> str:
    """Return a part as a percentage, such as "58%", or a dash when it is not known."""
    return texts.text("no_value") if value is None else f"{round(100 * value)}%"


def _legend(items: list[tuple[tuple, str, dict]]) -> BoxLayout:
    """Make a row with a colored square and a name for each item (color, text key, values of the text)."""
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22), spacing=dp(6))
    for color, key, values in items:
        square = Widget(size_hint=(None, None), size=(dp(14), dp(14)))
        set_background(square, color)
        holder = BoxLayout(size_hint=(None, 1), width=dp(14), padding=(0, dp(4)))
        holder.add_widget(square)
        name = Label(size_hint=(None, 1), color=theme.TEXT_COLOR, font_size=sp(13))
        name.bind(texture_size=lambda widget, size: setattr(widget, "width", size[0] + dp(12)))
        set_text(name, texts.lazy(key, **values))
        row.add_widget(holder)
        row.add_widget(name)
    row.add_widget(Widget())  # Keeps the items on the left.
    return row


def _label(make: Callable[[], str]):
    """Make a label that grows with its text, and follows the language."""
    label = growing_label()
    set_text(label, make)
    return label
