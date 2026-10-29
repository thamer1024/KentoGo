"""A KataGo that is started later than the app: when the main KataGo is ready, or by its first query.

The comparison model's KataGo should not load at the same time as the main one, which would
slow down the main KataGo, whose answers the user waits for first. So it is made without
starting it, and start_after_ready starts it in the background as soon as the main KataGo is
ready (a query that comes before that starts it at once). It runs until it is closed (when the
app closes, or the settings change it). Starting KataGo takes long (it loads the model and
prepares the GPU, which can take tens of seconds), so it is not stopped between queries.

Only the KataGo that KentoGo started itself is stopped. Other programs, such as
KaTrain, run their own KataGo processes, which are never touched.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Protocol

from kentogo.katago.locate import EngineCommand
from kentogo.katago.process import KataGoProcess

Callback = Callable[[dict], None]

READY_TIMEOUT = 600.0  # Seconds to wait for the main KataGo (its first start may tune itself for long).


class GetsReady(Protocol):
    """A KataGo that can be waited for until it is ready (KataGoProcess or OnDemandEngine)."""

    def wait_until_ready(self, timeout: float) -> bool:
        """Wait until KataGo is ready; return True if it is."""


class OnDemandEngine:
    """Starts KataGo when it is first needed, and stops it when asked to.

    It has the same query method as KataGoProcess, so it can be used in its place.

    Attributes:
        command: How to start KataGo.
    """

    def __init__(self, command: EngineCommand, make_process: Callable[[EngineCommand], KataGoProcess] = KataGoProcess):
        """Prepare to start KataGo. Nothing is started yet.

        Args:
            command: How to start KataGo.
            make_process: Makes the process (tests pass a fake one).
        """
        self.command = command
        self._make_process = make_process
        self._process: KataGoProcess | None = None
        self._closed = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """True while KentoGo's KataGo for this engine is running."""
        with self._lock:
            return self._process is not None and self._process.is_running

    def start(self) -> None:
        """Start KataGo before its first query, unless it runs already or the engine was closed.

        Raises:
            OSError: If KataGo cannot be started.
        """
        with self._lock:
            if not self._closed:
                self._running_process()

    def query(self, request: dict, callback: Callback) -> str:
        """Send a query, starting KataGo first if it is not running.

        Raises:
            OSError: If KataGo cannot be started.
            RuntimeError: If KataGo stopped just before the query.
        """
        with self._lock:
            process = self._running_process()
        return process.query(request, callback)

    def wait_until_ready(self, timeout: float) -> bool:
        """Wait until the started KataGo is ready to answer; False if it was not started or did not get ready."""
        with self._lock:
            process = self._process
        return process is not None and process.wait_until_ready(timeout)

    @property
    def ready_seconds(self) -> float | None:
        """How many seconds the running KataGo took to get ready, or None before it is ready."""
        with self._lock:
            process = self._process
        return process.ready_seconds if process is not None else None

    def stop(self) -> None:
        """Stop KataGo in the background, so that the screen does not wait for it to end."""
        with self._lock:
            process, self._process = self._process, None
        if process is not None:
            print("KataGo stopped (it is started again when needed)", file=sys.stderr)
            threading.Thread(target=process.close, name="katago-stop", daemon=True).start()

    def close(self) -> None:
        """Stop KataGo and wait for it to end (when the app closes, or the settings change it).

        A start in the background that comes after this does nothing (see start_after_ready).
        """
        with self._lock:
            self._closed = True
            process, self._process = self._process, None
        if process is not None:
            process.close()

    def _running_process(self) -> KataGoProcess:
        """Return the running KataGo, starting it if it is not running (the lock must be held)."""
        if self._process is None or not self._process.is_running:
            process = self._make_process(self.command)
            process.start()
            print("KataGo started: " + " ".join(self.command.command), file=sys.stderr)
            self._process = process
        return self._process


def start_after_ready(main: GetsReady, compare: OnDemandEngine, timeout: float = READY_TIMEOUT) -> threading.Thread:
    """Start the comparison model's KataGo in the background when the main KataGo is ready.

    When the main KataGo does not get ready (it could not start, or it stopped), the comparison
    model is left to start at its first query, as before.

    Args:
        main: The main KataGo, already started.
        compare: The comparison model's KataGo.
        timeout: The most seconds to wait for the main KataGo.

    Returns:
        The background thread (tests wait for it).
    """

    def work() -> None:
        if not main.wait_until_ready(timeout):
            print("the main KataGo is not ready: the comparison model is started when needed", file=sys.stderr)
            return
        try:
            compare.start()
        except OSError as error:  # Told to the user when the comparison model is asked.
            print(f"KataGo with the comparison model could not be started: {error}", file=sys.stderr)

    thread = threading.Thread(target=work, name="katago-compare-start", daemon=True)
    thread.start()
    return thread
