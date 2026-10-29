"""Tests for kentogo.katago.process, with a fake KataGo (fake_katago.py)."""

import sys
import threading
import time
from pathlib import Path

import pytest

from kentogo.katago.locate import EngineCommand
from kentogo.katago.process import KataGoProcess

FAKE_KATAGO = Path(__file__).with_name("fake_katago.py")
TIMEOUT = 10


class Answers:
    """Collects the answers of a query, and lets a test wait for the final one."""

    def __init__(self):
        """Start with no answers."""
        self.items: list[dict] = []
        self.done = threading.Event()

    def __call__(self, answer: dict) -> None:
        """Keep an answer, and note when the final one has come."""
        self.items.append(answer)
        if not answer.get("isDuringSearch"):
            self.done.set()

    def wait(self) -> dict:
        """Wait for the final answer and return it."""
        assert self.done.wait(TIMEOUT), "no answer from the fake KataGo"
        return self.items[-1]


@pytest.fixture
def katago():
    """Start the fake KataGo, and stop it after the test."""
    process = KataGoProcess(EngineCommand((sys.executable, str(FAKE_KATAGO)), False, 10))
    process.start()
    yield process
    process.close()


def test_query_and_answer(katago):
    """A query gets its answers: first during the search, then the final one."""
    answers = Answers()
    query_id = katago.query({"moves": [["B", "Q16"]]}, answers)
    final = answers.wait()
    assert final == {"id": query_id, "isDuringSearch": False, "moves": [["B", "Q16"]]}
    assert [a["isDuringSearch"] for a in answers.items] == [True, False]


def test_override_settings_are_not_sent_when_they_are_on_the_command_line():
    """With the settings on the command line, "overrideSettings" is left out of the queries."""
    command = EngineCommand((sys.executable, str(FAKE_KATAGO)), False, 10, settings_in_command=True)
    process = KataGoProcess(command)
    process.start()
    try:
        answers = Answers()
        process.query({"moves": [], "overrideSettings": {"reportAnalysisWinratesAs": "BLACK"}}, answers)
        assert "overrideSettings" not in answers.wait()
    finally:
        process.close()


def test_warning_is_not_the_answer(katago):
    """A warning about a query is skipped, and the real answer still reaches the callback."""
    answers = Answers()
    katago.query({"action": "warn", "moves": [["B", "C3"]]}, answers)
    assert answers.wait()["moves"] == [["B", "C3"]]
    assert all("warning" not in answer for answer in answers.items)


def test_broken_callback_does_not_stop_other_answers(katago):
    """An error in one callback does not stop the answers to the other queries."""

    def broken(_answer):
        raise RuntimeError("broken callback")

    katago.query({"moves": []}, broken)
    answers = Answers()
    katago.query({"moves": [["B", "D4"]]}, answers)
    assert answers.wait()["moves"] == [["B", "D4"]]


def test_answers_in_a_different_order(katago):
    """Each answer goes to the callback of its own query, even in a different order."""
    slow, fast = Answers(), Answers()
    slow_id = katago.query({"action": "slow", "moves": [["B", "A1"]]}, slow)
    fast_id = katago.query({"moves": [["B", "T19"]]}, fast)
    assert fast.wait()["id"] == fast_id
    assert slow.wait()["id"] == slow_id
    assert slow.wait()["moves"] == [["B", "A1"]]


def test_waiting_queries_fail_when_katago_stops(katago):
    """When KataGo stops, the waiting queries get an error with KataGo's error output."""
    waiting = Answers()
    katago.query({"action": "slow"}, waiting)
    katago.query({"action": "crash"}, Answers())
    error = waiting.wait()
    assert "error" in error
    assert not katago.is_running


def test_close_fails_waiting_queries(katago):
    """Closing KataGo gives an error answer to the waiting queries."""
    waiting = Answers()
    katago.query({"action": "slow"}, waiting)
    katago.close()
    assert "error" in waiting.wait()
    with pytest.raises(RuntimeError):
        katago.query({}, Answers())


def test_error_output_is_kept(katago):
    """KataGo's error output is kept for error messages.

    The error output is read by its own thread, which may be a moment later than
    the answer, so the test waits for it a little.
    """
    answers = Answers()
    katago.query({}, answers)
    answers.wait()
    deadline = time.monotonic() + 5
    while "fake KataGo started" not in katago.error_output() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "fake KataGo started" in katago.error_output()


def test_wait_until_ready(katago):
    """Waiting ends when KataGo says that it is ready; a stopped or unstarted KataGo is not ready."""
    assert katago.wait_until_ready(TIMEOUT)
    katago.query({"action": "crash"}, Answers())
    deadline = time.monotonic() + TIMEOUT
    while katago.is_running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not katago.wait_until_ready(TIMEOUT)
    assert not KataGoProcess(EngineCommand(("katago",), False, 10)).wait_until_ready(0.01)


def test_ready_without_the_message():
    """A KataGo that does not write that it is ready (its log is off) is ready when it answers query_version."""
    process = KataGoProcess(EngineCommand((sys.executable, str(FAKE_KATAGO), "--quiet"), False, 10))
    process.start()
    try:
        assert process.wait_until_ready(TIMEOUT) and process.ready_seconds is not None
        assert "ready to begin" not in process.error_output()
    finally:
        process.close()


def test_program_that_does_not_exist():
    """Starting a program that does not exist is an error."""
    process = KataGoProcess(EngineCommand(("/not/a/katago",), False, 10))
    with pytest.raises(OSError):
        process.start()
