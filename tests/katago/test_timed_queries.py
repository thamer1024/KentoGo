"""Tests for kentogo.katago.timed_queries."""

from kentogo.katago.timed_queries import RunningQueries, TimedEngine, _answer_line


class HeldEngine:
    """An engine that keeps the queries, so that a test answers them when it wants."""

    def __init__(self, name: str, sent: list):
        """Start with no queries. Every query sent to any engine is added to sent."""
        self.name = name
        self.sent = sent
        self.callbacks = []

    def query(self, request, callback):
        """Keep the query."""
        self.sent.append((self.name, request["n"]))
        self.callbacks.append(callback)
        return f"{self.name}{len(self.callbacks)}"


class TerminatingEngine(HeldEngine):
    """An engine that can stop reading a query."""

    def __init__(self, name: str, sent: list):
        super().__init__(name, sent)
        self.terminated = []

    def terminate(self, query_id):
        self.terminated.append(query_id)


class StoppedEngine:
    """An engine whose KataGo has stopped."""

    def query(self, request, callback):
        """Fail as KataGoProcess does when KataGo is not running."""
        raise RuntimeError("KataGo is not running")


def test_queries_are_sent_at_once_to_all_engines():
    """Every query goes to KataGo when it is asked for, without waiting for the answers before it."""
    sent, running = [], RunningQueries()
    main, compare = HeldEngine("main", sent), HeldEngine("compare", sent)
    answers = []
    assert TimedEngine(main, running).query({"n": 1}, answers.append) == "main1"
    TimedEngine(compare, running).query({"n": 2}, answers.append)
    TimedEngine(main, running).query({"n": 3}, answers.append)
    assert sent == [("main", 1), ("compare", 2), ("main", 3)] and running.count == 3
    main.callbacks[0]({"isDuringSearch": True})
    assert running.count == 3  # An answer during the search is passed on, but the query still runs.
    main.callbacks[0]({"isDuringSearch": False})
    compare.callbacks[0]({"isDuringSearch": False})
    assert running.count == 1 and len(answers) == 3


def test_errors_are_answers():
    """A stopped KataGo gives an error answer, and a broken callback does not stop the counting."""
    sent, running = [], RunningQueries()
    main = HeldEngine("main", sent)
    errors = []

    def broken(_answer):
        raise ValueError("broken")

    TimedEngine(main, running).query({"n": 1}, broken)
    assert TimedEngine(StoppedEngine(), running).query({"n": 2}, errors.append) == ""
    assert "KataGo could not take the query" in errors[0]["error"]
    main.callbacks[0]({"error": "bad query"})  # The broken callback raises, but the query is counted as done.
    assert running.count == 0


def test_the_line_of_an_answer_tells_its_visits_and_time():
    """The line written for each final answer tells the visits, the seconds and the queries still running."""
    assert (
        _answer_line({"rootInfo": {"visits": 740}}, 1.234, 2)
        == "KataGo answered: 740 visits in 1.2 s (2 queries running)"
    )
    assert "error" in _answer_line({"error": "x"}, 0.1, 0)


def test_a_query_is_terminated_by_the_engine_that_can():
    """terminate goes to KataGo; an engine without it does nothing."""
    sent, running = [], RunningQueries()
    engine = TerminatingEngine("main", sent)
    TimedEngine(engine, running).terminate("main1")
    TimedEngine(StoppedEngine(), running).terminate("x")
    assert engine.terminated == ["main1"]


def test_all_queries_are_terminated_by_the_engine_that_can():
    """terminate_all goes to KataGo; an engine without it does nothing."""

    class Stopping(HeldEngine):
        stopped = 0

        def terminate_all(self):
            self.stopped += 1

    engine = Stopping("main", [])
    TimedEngine(engine, RunningQueries()).terminate_all()
    TimedEngine(StoppedEngine(), RunningQueries()).terminate_all()
    assert engine.stopped == 1
