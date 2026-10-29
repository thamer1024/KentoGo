"""Tests for kentogo.katago.one_at_a_time."""

from kentogo.katago.one_at_a_time import OneAtATime, QueryLine


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
        return str(len(self.callbacks))

    def finish(self, index: int) -> None:
        """Answer a query: first during the search, then the final answer."""
        self.callbacks[index]({"isDuringSearch": True})
        self.callbacks[index]({"isDuringSearch": False, "n": index})


class StoppedEngine:
    """An engine whose KataGo has stopped."""

    def query(self, request, callback):
        """Fail as KataGoProcess does when KataGo is not running."""
        raise RuntimeError("KataGo is not running")


def test_queries_go_one_at_a_time_over_all_engines():
    """The next query is sent only after the final answer of the one before, in the order asked."""
    sent, line = [], QueryLine()
    main, compare = HeldEngine("main", sent), HeldEngine("compare", sent)
    answers = []
    OneAtATime(main, line).query({"n": 1}, answers.append)
    OneAtATime(compare, line).query({"n": 2}, answers.append)
    OneAtATime(main, line).query({"n": 3}, answers.append)
    assert sent == [("main", 1)] and line.waiting == 2
    main.callbacks[0]({"isDuringSearch": True})
    assert sent == [("main", 1)]  # An answer during the search does not send the next one.
    main.callbacks[0]({"isDuringSearch": False})
    assert sent == [("main", 1), ("compare", 2)]
    compare.finish(0)
    assert sent == [("main", 1), ("compare", 2), ("main", 3)]
    main.finish(1)
    assert line.waiting == 0 and len([a for a in answers if not a["isDuringSearch"]]) == 3


def test_errors_do_not_stop_the_line():
    """An error answer, a stopped KataGo, or a broken callback lets the next query go."""
    sent, line = [], QueryLine()
    main = HeldEngine("main", sent)
    errors = []

    def broken(_answer):
        raise ValueError("broken")

    OneAtATime(main, line).query({"n": 1}, broken)
    OneAtATime(StoppedEngine(), line).query({"n": 2}, errors.append)
    OneAtATime(main, line).query({"n": 3}, errors.append)
    main.callbacks[0]({"error": "bad query"})  # The broken callback raises, but the line goes on.
    assert "KataGo could not take the query" in errors[0]["error"]
    assert sent == [("main", 1), ("main", 3)]


def test_the_line_of_an_answer_tells_its_visits_and_time():
    """The line written for each final answer tells the visits, the seconds and the queries waiting."""
    from kentogo.katago.one_at_a_time import _answer_line

    assert (
        _answer_line({"rootInfo": {"visits": 740}}, 1.234, 2)
        == "KataGo answered: 740 visits in 1.2 s (2 queries waiting)"
    )
    assert "error" in _answer_line({"error": "x"}, 0.1, 0)
