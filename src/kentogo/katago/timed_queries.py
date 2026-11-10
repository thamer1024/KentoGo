"""Send the queries to KataGo at once, as KaTrain does, and write how long each one took.

KataGo's analysis engine reads several queries at the same time (numAnalysisThreads in its settings
file; KaTrain's analysis_config.cfg has 12) and starts them in the order of their priority. So each
query is sent as soon as it is asked for, to the main model's or the comparison model's KataGo,
and KataGo is never left waiting for the next query. Each query has a time limit (the engine's
max_time, KaTrain's "max_time"), so a slow computer does not make the user wait long.

The time of each final answer is written to the console (or the log) with its visits and the
number of queries still running, so that a slow computer or model can be found.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from collections.abc import Callable

Callback = Callable[[dict], None]


class RunningQueries:
    """Counts the queries that KataGo is reading, over all engines (see TimedEngine)."""

    def __init__(self):
        """Start with no queries."""
        self._lock = threading.Lock()
        self._count = 0

    @property
    def count(self) -> int:
        """How many queries are running."""
        with self._lock:
            return self._count

    def started(self) -> None:
        """Count a query that is sent."""
        with self._lock:
            self._count += 1

    def finished(self) -> int:
        """Count a query whose final answer has come, and return how many are still running."""
        with self._lock:
            self._count = max(0, self._count - 1)
            return self._count


class TimedEngine:
    """An engine that sends each query at once and writes the time of its final answer.

    It has the same query method as KataGoProcess, so it can be used in its place.
    """

    def __init__(self, engine, running: RunningQueries):
        """Wrap an engine.

        Args:
            engine: The KataGo engine (such as KataGoProcess or OnDemandEngine).
            running: The count of running queries, shared by all engines.
        """
        self.engine = engine
        self.running = running

    def query(self, request: dict, callback: Callback) -> str:
        """Send a query now; callback is called with each answer.

        When KataGo cannot take the query (it has stopped), callback gets an error answer.

        Returns:
            The id of the query, or "" when it could not be sent.
        """
        sent_at = time.monotonic()
        self.running.started()

        def receive(answer: dict) -> None:
            """Pass the answer on, and write the time of the final answer."""
            try:
                callback(answer)
            except Exception:  # An error of one caller must not stop KataGo's answers to the others.
                traceback.print_exc()
            if not answer.get("isDuringSearch"):
                left = self.running.finished()
                print(_answer_line(answer, time.monotonic() - sent_at, left), file=sys.stderr)

        try:
            return self.engine.query(request, receive)
        except (RuntimeError, OSError) as error:  # KataGo has stopped.
            receive({"error": f"KataGo could not take the query: {error}"})
            return ""

    def terminate(self, query_id: str) -> None:
        """Ask KataGo to stop reading a query, when the engine can (see process.KataGoProcess.terminate)."""
        terminate = getattr(self.engine, "terminate", None)
        if terminate is not None:
            terminate(query_id)

    def stop(self) -> None:
        """Stop the engine when it can be stopped and started again (see on_demand.OnDemandEngine)."""
        stop = getattr(self.engine, "stop", None)
        if stop is not None:
            stop()


def _answer_line(answer: dict, seconds: float, running: int) -> str:
    """Return the line written for a final answer: its visits, the time it took, and the queries still running."""
    visits = answer.get("rootInfo", {}).get("visits", "?") if "error" not in answer else "error"
    return f"KataGo answered: {visits} visits in {seconds:.1f} s ({running} queries running)"
