"""Measure how fast KataGo reads on this computer (the "測る" button of the recommended settings).

KataGo is asked to analyze positions of the opening, and the number of positions it read
(the visits of the root) is divided by the time it took. The first analysis is only a warm-up:
KataGo may still be getting ready (some versions tune themselves for the GPU at the first
start). Then the number of visits grows until one analysis takes at least MEASURE_SECONDS,
so that the time of sending the query and reading the answer does not count much. The GPU
may still be slow in the first analyses after the warm-up (it prepares itself for larger
batches of positions), so at least MIN_RUNS analyses are measured, and the fastest one counts.

Each analysis starts with another first move, so that KataGo cannot reuse what it read before
(it keeps the results of its neural network for the positions it has seen).

The numbers of visits are then made from the speeds (see MeasuredSpeed.preset): each analysis
should take about QUERY_SECONDS. After an answer, KataGo judges it with three analyses, and the
comparison model also analyzes three positions, so each of the two takes at most about five
seconds (with the comparison model's KataGo already started). A user who wants deeper or
quicker reading can change the visits on the settings screen.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from kentogo.common.types import Move, Position
from kentogo.katago.engine_settings import EngineSettings
from kentogo.katago.evaluate import AnalysisEngine
from kentogo.katago.presets import Preset
from kentogo.katago.queries import position_query

MEASURE_SECONDS = 2.0  # An analysis that is measured takes at least this long.
WARM_UP_VISITS = 8  # The visits of the first analysis, which is not measured.
FIRST_VISITS = 32  # The visits of the first measured analysis.
MAX_VISITS = 20000  # The most visits of one analysis (a very fast GPU reads this in a few seconds).
MAX_RUNS = 6  # The most measured analyses.
MIN_RUNS = 2  # The fewest measured analyses (the first one may be slow, see above).
ANSWER_TIMEOUT = 600.0  # Seconds to wait for one answer (KataGo's first start may tune itself for long).
OPENINGS = ("Q16", "D4", "Q4", "D16", "R17", "C3", "K10")  # The first move of each analysis.
EMPTY_BOARD = Position(19, 6.5, "japanese", (), (), "B")
QUERY_SECONDS = 1.6  # About how long one analysis should take with the visits made from a speed.
LEAST_VISITS = 5  # The fewest visits that are set (KataGo's first idea alone is not a judgement).
LEAST_ESTIMATE_VISITS = 3  # The fewest visits of the territory and the standing.
ESTIMATE_SHARE = 4  # The territory and the standing get a quarter of the main model's visits.
PRESET_MEASURED = "measured"  # The key of the preset made from measured speeds.


@dataclass(frozen=True)
class MeasuredSpeed:
    """The speeds of the KataGo processes on this computer (positions read per second).

    Attributes:
        main: The speed with the main model.
        compare: The speed with the comparison model, or None when it is not turned on.
    """

    main: float
    compare: float | None = None

    def preset(self, engine: EngineSettings) -> Preset:
        """Return the numbers of visits that fit the speeds (see QUERY_SECONDS), as a preset.

        The territory and the standing need only a shallow reading, so they get a quarter of the
        visits of the main model. Without a measured comparison model, its visits stay as they are.
        """
        main = visits_for(self.main)
        compare = visits_for(self.compare) if self.compare is not None else engine.compare_max_visits
        estimate = max(LEAST_ESTIMATE_VISITS, round_visits(main / ESTIMATE_SHARE))
        return Preset(PRESET_MEASURED, main, compare, estimate, round(self.main), round(self.compare or 0))


def visits_for(speed: float) -> int:
    """Return the visits that one analysis reads in about QUERY_SECONDS at a speed (at least LEAST_VISITS)."""
    return max(LEAST_VISITS, round_visits(speed * QUERY_SECONDS))


def round_visits(visits: float) -> int:
    """Round a number of visits to two significant digits, such as 739 to 740 or 1234 to 1200."""
    whole = int(visits)
    if whole < 100:
        return whole
    digits = len(str(whole)) - 2
    return round(whole, -digits)


def measure_speed(analyze: Callable[[dict], dict], clock: Callable[[], float] = time.monotonic) -> float:
    """Measure KataGo's speed.

    Args:
        analyze: Sends a query to KataGo and returns its final answer (see wait_for_answer).
        clock: Returns the time in seconds (tests give a fake one).

    Returns:
        The positions that KataGo reads per second (visits per second), in its fastest measured analysis.

    Raises:
        ValueError: If KataGo answers with an error, or its answer has no visits.
    """
    analyze(opening_query(0, WARM_UP_VISITS))
    visits = FIRST_VISITS
    fastest = 0.0
    for run in range(1, MAX_RUNS + 1):
        start = clock()
        answer = analyze(opening_query(run, visits))
        elapsed = max(clock() - start, 0.001)
        speed = root_visits(answer) / elapsed
        fastest = max(fastest, speed)
        if run >= MIN_RUNS and (elapsed >= MEASURE_SECONDS or visits >= MAX_VISITS):
            break
        if elapsed < MEASURE_SECONDS:  # Otherwise the same visits are measured again.
            visits = next_visits(visits, fastest)
    return fastest


def next_visits(visits: int, speed: float) -> int:
    """Return the visits of the next analysis: enough for a bit more than MEASURE_SECONDS at the speed seen.

    It at least doubles, so that the measuring ends soon even when the first analyses are slow to start.
    """
    return min(MAX_VISITS, max(visits * 2, int(speed * MEASURE_SECONDS * 1.2)))


def opening_query(run: int, visits: int) -> dict:
    """Make the query of one analysis: the position after a first move of OPENINGS (another one each run)."""
    first_move = Move.from_gtp(OPENINGS[run % len(OPENINGS)], "B")
    return position_query(EMPTY_BOARD, (first_move,), visits)


def root_visits(answer: dict) -> int:
    """Return how many positions KataGo read for an answer.

    Raises:
        ValueError: If the answer is an error, or has no visits.
    """
    if "error" in answer:
        raise ValueError(f"KataGo could not analyze the position: {answer['error']}")
    try:
        return int(answer["rootInfo"]["visits"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"KataGo's answer has no visits: {answer}") from error


def wait_for_answer(engine: AnalysisEngine, query: dict, timeout: float = ANSWER_TIMEOUT) -> dict:
    """Send a query and wait for KataGo's final answer (the answers during the search are skipped).

    Raises:
        TimeoutError: If no final answer comes in time.
    """
    done = threading.Event()
    answers: list[dict] = []

    def receive(answer: dict) -> None:
        if answer.get("isDuringSearch"):
            return
        answers.append(answer)
        done.set()

    engine.query(query, receive)
    if not done.wait(timeout):
        raise TimeoutError(f"KataGo did not answer in {timeout:.0f} seconds")
    return answers[0]
