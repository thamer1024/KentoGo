"""Run KataGo's analysis engine as a separate process, and talk to it.

KataGo's analysis engine reads one JSON query per line, and writes one JSON
answer per line. Each query has an "id", and the answer has the same "id".
Answers can come back in a different order than the queries.
See https://github.com/lightvector/KataGo/blob/master/docs/Analysis_Engine.md

The answers are read in a background thread, and the callback of each query
is called in that thread. A screen must pass the result to its main thread
(for Kivy, with Clock.schedule_once) before it changes any widget.
KataGo's warnings about a query are printed and skipped, and an error in one
callback is printed, so that the answers to the other queries still arrive.
On Windows, KataGo is started without a console window of its own.

KataGo is ready when it has loaded its model and prepared the GPU. It says so in its error
output ("ready to begin handling requests"), but only when it writes its log there, which the
settings file can turn off. So a query_version query is also sent at the start: KataGo reads
queries only when it is ready, so its answer tells it too. Whichever comes first counts.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable

from kentogo.katago.locate import EngineCommand

Callback = Callable[[dict], None]

# Number of lines of KataGo's error output that are kept for error messages.
STDERR_LINES_KEPT = 50
READY_MESSAGE = "ready to begin handling requests"  # KataGo writes this when it has started.
VERSION_QUERY = {"action": "query_version"}  # Answered as soon as KataGo is ready.

# On Windows, a console program started from a program with a window opens a black console
# window of its own. This flag stops that. Other systems have no such flag (0 means none).
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _is_warning(answer: dict) -> bool:
    """True for KataGo's warning about a query, such as {"id": ..., "field": ..., "warning": ...}.

    A warning is not the answer: the analysis (or an error) for the same id comes after it.
    """
    return "warning" in answer and not any(key in answer for key in ("rootInfo", "moveInfos", "error"))


class KataGoProcess:
    """One running KataGo analysis engine.

    Several queries can be sent at the same time. KataGo is started by start(),
    and must be stopped with close() when it is no longer needed.
    """

    def __init__(self, command: EngineCommand):
        """Prepare to run KataGo. It is not started yet.

        Args:
            command: How to start KataGo (see katago.locate.engine_command).
        """
        self.command = command
        self._process: subprocess.Popen | None = None
        self._callbacks: dict[str, Callback] = {}
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._stderr: deque[str] = deque(maxlen=STDERR_LINES_KEPT)
        self._started_at = 0.0
        self._ready = threading.Event()  # Set when KataGo says that it is ready, or when its output ends.
        self._ready_seconds: float | None = None  # How long KataGo took to get ready.

    def start(self) -> None:
        """Start KataGo, and the background threads that read its output.

        Raises:
            OSError: If the program cannot be started.
        """
        command = self.command.command[0] if self.command.shell else list(self.command.command)
        self._started_at = time.monotonic()
        self._process = subprocess.Popen(
            command,
            shell=self.command.shell,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=_NO_WINDOW,
        )
        threading.Thread(target=self._read_answers, name="katago-stdout", daemon=True).start()
        threading.Thread(target=self._read_errors, name="katago-stderr", daemon=True).start()
        try:
            self.query(VERSION_QUERY, self._answered_version)
        except (RuntimeError, OSError):  # KataGo stopped at once: _read_errors ends the waiting.
            pass

    @property
    def is_running(self) -> bool:
        """True while the KataGo process is running."""
        return self._process is not None and self._process.poll() is None

    def query(self, request: dict, callback: Callback) -> str:
        """Send a query to KataGo.

        Args:
            request: The query, without "id" (see KataGo's Analysis_Engine.md). Its "overrideSettings"
                is not sent when the settings are on the command line.
            callback: Called with each answer for this query, in the background thread.
                An answer with the key "error" means that the query failed.

        Returns:
            The id given to the query.

        Raises:
            RuntimeError: If KataGo is not running.
            OSError: If KataGo stopped just before the query was written.
        """
        if not self.is_running:
            raise RuntimeError("KataGo is not running")
        query_id = f"kentogo-{next(self._ids)}"
        if self.command.settings_in_command:
            # The settings are on the command line (see locate.fixed_settings).
            request = {key: value for key, value in request.items() if key != "overrideSettings"}
        line = json.dumps({**request, "id": query_id}) + "\n"
        with self._lock:
            self._callbacks[query_id] = callback
            self._process.stdin.write(line)
            self._process.stdin.flush()
        return query_id

    def close(self) -> None:
        """Stop KataGo. Queries that are still waiting get an error answer."""
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self._fail_waiting_queries("KataGo was stopped")

    def wait_until_ready(self, timeout: float) -> bool:
        """Wait until KataGo says that it is ready to answer (it loads the model and prepares the GPU first).

        Args:
            timeout: The most seconds to wait.

        Returns:
            True if KataGo is ready and running; False if it was not started, stopped, or did not get ready in time.
        """
        return self._process is not None and self._ready.wait(timeout) and self.is_running

    @property
    def ready_seconds(self) -> float | None:
        """How many seconds KataGo took from its start until it was ready, or None before it is ready."""
        return self._ready_seconds

    def error_output(self) -> str:
        """Return the last lines that KataGo wrote to its error output (useful for error messages)."""
        return "\n".join(self._stderr)

    def _read_answers(self) -> None:
        """Read KataGo's answers and call the callbacks (runs in a background thread)."""
        for line in self._process.stdout:
            try:
                answer = json.loads(line)
            except json.JSONDecodeError:
                continue  # KataGo writes only JSON here, so this should not happen.
            if _is_warning(answer):
                # A warning about the query (for example an unknown field). The real answer still comes.
                print(f"KataGo warning: {answer}", file=sys.stderr)
                continue
            callback = self._callback_for(answer)
            if callback is not None:
                try:
                    callback(answer)
                except Exception:  # One broken callback must not stop the answers of all other queries.
                    traceback.print_exc()
        self._process.wait()  # The output has ended, so KataGo has stopped (or is stopping).
        self._fail_waiting_queries("KataGo stopped: " + self.error_output())

    def _callback_for(self, answer: dict) -> Callback | None:
        """Return the callback of the query that an answer belongs to.

        The callback is forgotten after the final answer. An answer with
        "isDuringSearch": true is not final, so more answers will come.
        """
        query_id = answer.get("id")
        with self._lock:
            if answer.get("isDuringSearch"):
                return self._callbacks.get(query_id)
            return self._callbacks.pop(query_id, None)

    def _read_errors(self) -> None:
        """Keep the last lines of KataGo's error output (runs in a background thread).

        When KataGo says that it is ready, the time that it took to start is written to the
        console (or the log), as starting can take long (loading the model, preparing the GPU).
        """
        for line in self._process.stderr:
            self._stderr.append(line.rstrip())
            if READY_MESSAGE in line:
                self._got_ready()
        self._ready.set()  # KataGo has stopped: nobody should wait for it any more.

    def _answered_version(self, answer: dict) -> None:
        """Take the answer to query_version as the sign that KataGo is ready (an error answer means it stopped)."""
        if "error" not in answer:
            self._got_ready()

    def _got_ready(self) -> None:
        """Keep how long KataGo took to get ready (the first time only), and end the waiting for it."""
        if self._ready_seconds is None:
            self._ready_seconds = time.monotonic() - self._started_at
            print(f"KataGo is ready ({self._ready_seconds:.1f} s after it was started)", file=sys.stderr)
        self._ready.set()

    def _fail_waiting_queries(self, message: str) -> None:
        """Give an error answer to every query that is still waiting."""
        with self._lock:
            waiting = list(self._callbacks.items())
            self._callbacks.clear()
        for query_id, callback in waiting:
            callback({"id": query_id, "error": message})
