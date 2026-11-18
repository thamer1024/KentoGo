"""The texts of the report (成績表) and of the summary of the day."""

from __future__ import annotations

from collections.abc import Sequence

from kentogo.fights_today import FightSummary
from kentogo.gui import texts
from kentogo.repetition.counts import ProblemCounts
from kentogo.report import RECENT, GameAverages, Recent, TodaySummary, Totals


def _percent(value: float | None) -> str:
    """Return a part (0.0 to 1.0) as a percentage such as "72%", or a dash when it is not known."""
    return texts.text("no_value") if value is None else f"{round(100 * value)}%"


def _per_game(value: float | None) -> str:
    """Return an average number of mistakes per game with one decimal, or a dash when it is not known."""
    return texts.text("no_value") if value is None else f"{value:.1f}"


def _trend(now: float | None, before: float | None) -> str:
    """Return an arrow when a part went up or down by at least TREND_STEP, else ""."""
    if now is None or before is None or abs(now - before) < TREND_STEP:
        return ""
    return texts.text("trend_up") if now > before else texts.text("trend_down")


TREND_STEP = 0.02  # A change smaller than this (2 points of percentage) shows no arrow.


def totals_text(totals: Totals) -> str:
    """Return the lines of the report about all the practice."""
    return texts.text(
        "report_totals",
        answered=totals.answered,
        correct=totals.correct,
        finished=totals.finished,
        recovered=f"{totals.recovered:,.0f}",
        days=totals.days,
    )


def recent_text(recent: Recent) -> str:
    """Return the lines of the report about the latest practice days, compared with the ones before."""
    if recent.correct_rate is None:
        return texts.text("report_recent_none")
    return texts.text(
        "report_recent",
        count=RECENT,
        rate=_percent(recent.correct_rate),
        rate_trend=_trend(recent.correct_rate, recent.earlier_correct_rate),
        average=_percent(recent.average),
        average_trend=_trend(recent.average, recent.earlier_average),
        earlier_rate=_percent(recent.earlier_correct_rate),
        earlier_average=_percent(recent.earlier_average),
    )


def fight_totals_text(totals: Totals) -> str:
    """Return the lines of the report about all the local fights."""
    return texts.text(
        "report_fight_totals",
        answered=totals.answered,
        correct=totals.correct,
        finished=totals.finished,
        days=totals.days,
    )


def fight_recent_text(recent: Recent) -> str:
    """Return the lines of the report about the latest practice days of the local fights."""
    if recent.correct_rate is None:
        return texts.text("report_recent_none")
    return texts.text(
        "report_fight_recent",
        count=RECENT,
        rate=_percent(recent.correct_rate),
        rate_trend=_trend(recent.correct_rate, recent.earlier_correct_rate),
        earlier_rate=_percent(recent.earlier_correct_rate),
    )


def points(value: float) -> str:
    """Return a number of points without a needless decimal, such as "3" or "2.5"."""
    return f"{value:g}"


def band_key(bands: Sequence[float], index: int) -> tuple[str, dict]:
    """Return the text key and its values naming one band of mistakes (bands: the lower ends, the biggest first)."""
    if index == 0:
        return "band_top", {"low": points(bands[0])}
    return "band_range", {"low": points(bands[index]), "high": points(bands[index - 1])}


def band_names(bands: Sequence[float]) -> list[str]:
    """Return the names of the bands of mistakes, such as "20目以上" and "10〜20目"."""
    return [texts.text(key, **values) for key, values in (band_key(bands, index) for index in range(len(bands)))]


def game_averages_text(averages: GameAverages, bands: Sequence[float]) -> str:
    """Return the lines of the report about the mistakes per game in each band, the latest games and the ones before."""
    if averages.latest is None:
        return texts.text("report_games_none")
    names = band_names(bands)

    def joined(values: Sequence[float] | None) -> str:
        if values is None:
            return texts.text("no_value")
        return "　".join(f"{name} {_per_game(value)}" for name, value in zip(names, values, strict=True))

    return texts.text(
        "report_games_recent", count=RECENT, latest=joined(averages.latest), earlier=joined(averages.earlier)
    )


def problem_counts_text(counts: ProblemCounts) -> str:
    """Return the lines about how far the current problems are."""
    return texts.text(
        "problem_counts",
        total=counts.total,
        done=counts.done,
        in_progress=counts.in_progress,
        untouched=counts.untouched,
    )


def fight_summary_text(summary: FightSummary) -> str:
    """Return the summary of the day for the local fights, and how far the current fights are."""
    answers = texts.text("fight_summary", answered=summary.answered, correct=summary.correct)
    return f"{answers}\n\n{problem_counts_text(summary.counts)}"


def today_summary_text(summary: TodaySummary) -> str:
    """Return the summary of the day, with a line for each thing achieved today and the current problems."""
    lines = [
        texts.text(
            "today_summary",
            answered=summary.answered,
            correct=summary.correct,
            recovered=f"{summary.recovered:,.0f}",
            day=summary.day_number,
        )
    ]
    lines += [texts.text(f"achievement_{item.key}", value=f"{item.value:,.0f}") for item in summary.achievements]
    lines += ["", problem_counts_text(summary.counts)]
    return "\n".join(lines)
