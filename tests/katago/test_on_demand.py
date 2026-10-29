"""Tests for kentogo.katago.on_demand, with a fake process."""

import pytest

from kentogo.katago.locate import EngineCommand
from kentogo.katago.on_demand import OnDemandEngine, start_after_ready

COMMAND = EngineCommand(("katago", "analysis"), False, 10)


class FakeProcess:
    """A process that only records what happens to it."""

    made = []

    def __init__(self, command):
        """Remember the new process."""
        self.command = command
        self.is_running = False
        self.queries = []
        FakeProcess.made.append(self)

    def start(self):
        """Pretend to start."""
        self.is_running = True

    def query(self, request, callback):
        """Keep the query."""
        self.queries.append(request)
        return "1"

    def close(self):
        """Pretend to stop."""
        self.is_running = False

    def wait_until_ready(self, timeout):
        """Ready at once while running."""
        return self.is_running


class Main:
    """The main KataGo, ready or not."""

    def __init__(self, ready):
        """Remember whether it gets ready."""
        self.ready = ready

    def wait_until_ready(self, timeout):
        """Answer at once."""
        return self.ready


@pytest.fixture(autouse=True)
def no_processes():
    """Start each test with no fake processes."""
    FakeProcess.made = []


def test_started_by_the_first_query_and_kept_for_the_next():
    """KataGo is started by the first query, and the next queries use the same KataGo."""
    engine = OnDemandEngine(COMMAND, FakeProcess)
    assert not engine.is_running and FakeProcess.made == []
    engine.query({"n": 1}, print)
    engine.query({"n": 2}, print)
    assert len(FakeProcess.made) == 1 and FakeProcess.made[0].queries == [{"n": 1}, {"n": 2}]
    assert engine.is_running


def test_stopped_and_started_again():
    """After stop, KataGo ends, and the next query starts a new one."""
    engine = OnDemandEngine(COMMAND, FakeProcess)
    engine.query({"n": 1}, print)
    engine.stop()
    assert not engine.is_running  # The engine lets go of KataGo at once; it ends in the background.
    engine.query({"n": 2}, print)
    assert len(FakeProcess.made) == 2 and FakeProcess.made[1].queries == [{"n": 2}]
    engine.close()
    assert not FakeProcess.made[1].is_running


def test_stop_without_katago_does_nothing():
    """Stopping before the first query does nothing."""
    engine = OnDemandEngine(COMMAND, FakeProcess)
    engine.stop()
    engine.close()
    assert FakeProcess.made == []


def test_started_before_the_first_query():
    """start starts KataGo once; the queries then use it, and it is not started again."""
    engine = OnDemandEngine(COMMAND, FakeProcess)
    assert not engine.wait_until_ready(1)  # Not started yet.
    engine.start()
    engine.start()
    engine.query({"n": 1}, print)
    assert len(FakeProcess.made) == 1 and engine.is_running and engine.wait_until_ready(1)
    engine.close()


def test_no_start_after_close():
    """A start that comes after the screen was left (a late background start) does nothing."""
    engine = OnDemandEngine(COMMAND, FakeProcess)
    engine.close()
    engine.start()
    assert FakeProcess.made == [] and not engine.is_running


def test_the_comparison_model_starts_when_the_main_one_is_ready():
    """The comparison model's KataGo is started in the background when the main KataGo is ready."""
    compare = OnDemandEngine(COMMAND, FakeProcess)
    start_after_ready(Main(ready=True), compare).join(5)
    assert compare.is_running
    compare.close()


def test_the_comparison_model_waits_for_its_query_when_the_main_one_is_not_ready():
    """When the main KataGo does not get ready, the comparison model is started only by its first query."""
    compare = OnDemandEngine(COMMAND, FakeProcess)
    start_after_ready(Main(ready=False), compare).join(5)
    assert not compare.is_running and FakeProcess.made == []
