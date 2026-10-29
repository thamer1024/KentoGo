"""Send KataGo only one query at a time, over all KataGo processes.

KentoGo can run two KataGo processes (the main model and the comparison model).
KataGo's settings for KaTrain are usually made for one KataGo that uses the whole
GPU (and on Apple Silicon also the Neural Engine). When several queries run at
the same time, they share the GPU and each of them becomes slow, so the result
of the answer, which the user waits for, comes late.

So the queries wait in one line, and the next query is sent only when the final
answer (or an error) of the one before has come. They are sent in the order they
were asked for, so the answer is judged first, and the sequences come after it.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable

Callback = Callable[[dict], None]


class QueryLine:
    """The line of queries that waits for KataGo. It is shared by all engines (see OneAtATime)."""

    def __init__(self):
        """Start with no queries."""
        self._lock = threading.Lock()
        self._waiting: deque[tuple[object, dict, Callback]] = deque()
        self._running = False

    @property
    def waiting(self) -> int:
        """How many queries wait (not counting the one that is running)."""
        with self._lock:
            return len(self._waiting)

    def submit(self, engine, request: dict, callback: Callback) -> None:
        """Send a query now if no query is running, or put it at the end of the line.

        Args:
            engine: The KataGo engine (an object with a query method, such as KataGoProcess).
            request: The query.
            callback: Called with each answer of the query.
        """
        with self._lock:
            if self._running:
                self._waiting.append((engine, request, callback))
                return
            self._running = True
        self._send(engine, request, callback)

    def _send(self, engine, request: dict, callback: Callback) -> None:
        """Send one query. When its final answer comes, the next query in the line is sent.

        The time that each query took is written to the console (or the log), with the visits
        that KataGo read, so that a slow computer or model can be found.
        """
        sent_at = time.monotonic()

        def receive(answer: dict) -> None:
            """Pass the answer on, and go on with the line after the final answer."""
            try:
                callback(answer)
            except Exception:  # An error of one caller must not stop the line.
                traceback.print_exc()
            if not answer.get("isDuringSearch"):
                print(_answer_line(answer, time.monotonic() - sent_at, self.waiting), file=sys.stderr)
                self._next()

        try:
            engine.query(request, receive)
        except (RuntimeError, OSError) as error:  # KataGo has stopped.
            receive({"error": f"KataGo could not take the query: {error}"})

    def _next(self) -> None:
        """Send the next query in the line, if there is one."""
        with self._lock:
            if not self._waiting:
                self._running = False
                return
            engine, request, callback = self._waiting.popleft()
        self._send(engine, request, callback)


class OneAtATime:
    """An engine whose queries wait in a QueryLine shared with other engines.

    It has the same query method as KataGoProcess, so it can be used in its place.
    """

    def __init__(self, engine, line: QueryLine):
        """Wrap an engine.

        Args:
            engine: The KataGo engine (such as KataGoProcess).
            line: The line shared by all engines.
        """
        self.engine = engine
        self.line = line

    def query(self, request: dict, callback: Callback) -> str:
        """Put a query in the line. It is sent to KataGo when the queries before it have finished.

        Returns:
            "" (the id is given when the query is sent).
        """
        self.line.submit(self.engine, request, callback)
        return ""

    def stop(self) -> None:
        """Stop the engine when it can be stopped and started again (see on_demand.OnDemandEngine)."""
        stop = getattr(self.engine, "stop", None)
        if stop is not None:
            stop()


def _answer_line(answer: dict, seconds: float, waiting: int) -> str:
    """Return the line written for a final answer: its visits, the time it took, and the queries waiting."""
    visits = answer.get("rootInfo", {}).get("visits", "?") if "error" not in answer else "error"
    return f"KataGo answered: {visits} visits in {seconds:.1f} s ({waiting} queries waiting)"
