"""Tests for kentogo.katago.process, with a fake KataGo (fake_katago.py)."""

import sys
import threading
import time
from pathlib import Path

import pytest

from kentogo.katago.locate import EngineCommand
from kentogo.katago.process import MAX_RESTARTS, KataGoProcess

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


def wait_for_a_new_process(katago, old) -> None:
    """Wait until KataGo has been started again (another process than old)."""
    deadline = time.monotonic() + TIMEOUT
    while (katago._process is old or not katago.is_running) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert katago._process is not old and katago.is_running


def test_katago_is_started_again_when_it_stops(katago):
    """When KataGo stops by itself, it is started again: a waiting control action gets an error, and the next
    query is answered."""
    waiting = Answers()
    katago.query({"action": "slow"}, waiting)
    old = katago._process
    katago.query({"action": "crash"}, Answers())
    assert "error" in waiting.wait()
    wait_for_a_new_process(katago, old)
    answers = Answers()
    katago.query({"moves": [["B", "D4"]]}, answers)
    assert answers.wait()["moves"] == [["B", "D4"]]


def test_a_waiting_analysis_is_sent_again_to_the_new_katago(katago):
    """An analysis that waited when KataGo stopped is sent to the new KataGo, and gets its answer there."""
    held = Answers()
    katago.query({"hold": True, "moves": [["B", "C3"]]}, held)
    old = katago._process
    katago.query({"action": "crash"}, Answers())
    wait_for_a_new_process(katago, old)
    katago.query({"moves": []}, Answers())  # The new KataGo holds the query sent again until the next one.
    final = held.wait()
    assert final["moves"] == [["B", "C3"]] and "error" not in final


def test_a_katago_that_cannot_start_is_not_started_again_and_again():
    """After MAX_RESTARTS starts without an answer, KataGo is given up: the next query is an error."""
    process = KataGoProcess(EngineCommand((sys.executable, "-c", "import sys; sys.exit(1)"), False, 10))
    process.start()
    try:
        deadline = time.monotonic() + TIMEOUT
        while process._process is not None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert process._restarts == MAX_RESTARTS and not process.is_running
        with pytest.raises(RuntimeError):
            process.query({"moves": []}, Answers())
    finally:
        process.close()


def test_a_katago_that_hangs_is_started_again():
    """KataGo writes nothing while an analysis waits: it is started again and the analysis is sent again once.
    It hangs again on the same analysis, which then gets an error; the next analysis is answered."""
    process = KataGoProcess(EngineCommand((sys.executable, str(FAKE_KATAGO)), False, 10), 0.5, 0.05)
    process.start()
    try:
        assert process.wait_until_ready(TIMEOUT)
        frozen = Answers()
        first = process._process
        process.query({"freeze": True}, frozen)
        error = frozen.wait()  # Started again twice: the analysis was sent again only once.
        assert "error" in error and process._process is not first
        wait_for_a_new_process(process, first)
        answers = Answers()
        process.query({"moves": [["W", "E5"]]}, answers)
        assert answers.wait()["moves"] == [["W", "E5"]]
    finally:
        process.close()


def test_a_long_quiet_time_without_a_waiting_analysis_is_no_hang():
    """KataGo may write nothing while nothing waits (between problems): it is not started again."""
    process = KataGoProcess(EngineCommand((sys.executable, str(FAKE_KATAGO)), False, 10), 0.2, 0.05)
    process.start()
    try:
        assert process.wait_until_ready(TIMEOUT)
        first = process._process
        time.sleep(0.6)
        assert process._process is first and process._restarts == 0
    finally:
        process.close()


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
    """Waiting ends when KataGo says that it is ready; a closed or unstarted KataGo is not ready."""
    assert katago.wait_until_ready(TIMEOUT)
    katago.close()
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


def test_terminate_sends_katagos_terminate_action(katago, monkeypatch):
    """terminate asks KataGo to stop reading a query; without a running KataGo or an id, nothing is sent."""
    sent = []
    monkeypatch.setattr(katago, "query", lambda request, callback: sent.append(request) or "t")
    katago.terminate("kentogo-7")
    katago.terminate("")
    assert sent == [{"action": "terminate", "terminateId": "kentogo-7"}]
    stopped = KataGoProcess(EngineCommand((sys.executable, str(FAKE_KATAGO)), False, 10))
    stopped.terminate("kentogo-1")  # Not started: nothing happens.


def test_terminate_all_sends_katagos_terminate_all_action(katago, monkeypatch):
    """terminate_all asks KataGo to stop reading all queries; without a running KataGo, nothing is sent."""
    sent = []
    monkeypatch.setattr(katago, "query", lambda request, callback: sent.append(request) or "t")
    katago.terminate_all()
    assert sent == [{"action": "terminate_all"}]
    KataGoProcess(EngineCommand((sys.executable, str(FAKE_KATAGO)), False, 10)).terminate_all()  # Not started.
