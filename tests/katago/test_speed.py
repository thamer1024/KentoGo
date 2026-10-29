"""Tests for kentogo.katago.speed."""

import threading

import pytest

from kentogo.katago.engine_settings import EngineSettings
from kentogo.katago.speed import (
    FIRST_VISITS,
    MAX_VISITS,
    MEASURE_SECONDS,
    WARM_UP_VISITS,
    MeasuredSpeed,
    measure_speed,
    next_visits,
    opening_query,
    root_visits,
    round_visits,
    wait_for_answer,
)


class FakeKataGo:
    """Answers each query at once with all its visits, taking a fake time (visits / speed seconds)."""

    def __init__(self, speed: float):
        self.speed = speed
        self.now = 0.0
        self.queries: list[dict] = []

    def clock(self) -> float:
        return self.now

    def analyze(self, query: dict) -> dict:
        self.queries.append(query)
        self.now += query["maxVisits"] / self.speed
        return {"rootInfo": {"visits": query["maxVisits"]}}


@pytest.mark.parametrize("speed", [5.0, 40.0, 700.0, 3000.0])
def test_the_speed_is_measured_on_a_long_enough_analysis(speed):
    """After a warm-up, the visits grow until an analysis takes long enough; the speed is then right."""
    katago = FakeKataGo(speed)
    assert measure_speed(katago.analyze, katago.clock) == pytest.approx(speed)
    visits = [query["maxVisits"] for query in katago.queries]
    assert visits[:2] == [WARM_UP_VISITS, FIRST_VISITS]
    assert visits[-1] / speed >= MEASURE_SECONDS or visits[-1] == MAX_VISITS
    assert len(visits) <= 5  # A few analyses are enough, even on a very slow or a very fast computer.


class SlowFirstKataGo(FakeKataGo):
    """A KataGo whose first measured analysis is slow (the GPU is still preparing itself)."""

    def analyze(self, query: dict) -> dict:
        if len(self.queries) == 1:  # After the warm-up.
            self.now += 10.0
        return super().analyze(query)


def test_a_slow_first_analysis_does_not_count():
    """The fastest of at least two measured analyses is the speed."""
    katago = SlowFirstKataGo(600.0)
    assert measure_speed(katago.analyze, katago.clock) == pytest.approx(600.0)


def test_each_analysis_starts_with_another_move():
    """KataGo cannot reuse what it read for an earlier analysis."""
    first_moves = [opening_query(run, 10)["moves"][0][1] for run in range(4)]
    assert len(set(first_moves)) == 4


def test_the_visits_grow_at_least_twice():
    """A slow start does not make the measuring long, and the visits never pass the largest number."""
    assert next_visits(32, 1.0) == 64
    assert next_visits(32, 1000.0) == int(1000 * MEASURE_SECONDS * 1.2)
    assert next_visits(MAX_VISITS // 2, 1e9) == MAX_VISITS


def test_an_error_of_katago_is_told():
    """An error answer, or an answer without visits, is an error of the measuring."""
    with pytest.raises(ValueError):
        root_visits({"error": "bad query"})
    with pytest.raises(ValueError):
        root_visits({"rootInfo": {}})


class ThreadedEngine:
    """Answers in a background thread: first during the search, then the final answer."""

    def query(self, request, callback):
        def answer():
            callback({"isDuringSearch": True, "rootInfo": {"visits": 1}})
            callback({"isDuringSearch": False, "rootInfo": {"visits": request["maxVisits"]}})

        threading.Thread(target=answer).start()
        return "1"


class SilentEngine:
    """Never answers."""

    def query(self, request, callback):
        return "1"


def test_wait_for_the_final_answer():
    """The answers during the search are skipped; no answer in time is an error."""
    assert wait_for_answer(ThreadedEngine(), {"maxVisits": 50})["rootInfo"]["visits"] == 50
    with pytest.raises(TimeoutError):
        wait_for_answer(SilentEngine(), {"maxVisits": 50}, timeout=0.05)


def test_visits_are_made_from_the_speeds():
    """Each model gets the visits it reads in about 1.6 seconds; 地と形勢 gets a quarter of the main model's."""
    preset = MeasuredSpeed(616, 120).preset(EngineSettings(compare_max_visits=999))
    assert (preset.max_visits, preset.compare_max_visits, preset.estimate_visits) == (980, 190, 240)


def test_without_the_comparison_model_its_visits_stay():
    """A comparison model that was not measured keeps its visits; a very slow computer gets the fewest visits."""
    preset = MeasuredSpeed(3).preset(EngineSettings(compare_max_visits=999))
    assert (preset.max_visits, preset.compare_max_visits, preset.estimate_visits) == (5, 999, 3)


def test_round_visits():
    """The visits are rounded to two significant digits."""
    assert [round_visits(v) for v in (8, 73.9, 739, 1234, 20999)] == [8, 73, 740, 1200, 21000]
