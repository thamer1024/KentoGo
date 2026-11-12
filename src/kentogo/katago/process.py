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

When KataGo stops by itself (it crashed, or its output cannot be read or its input cannot be written),
it is started again at once, with the same command, and the queries that were waiting are sent to it again,
each once (a query that was already sent again gets an error answer, so that a query that makes KataGo
crash cannot start it again and again). A query sent while KataGo is stopped starts it again too. Control
actions (such as "terminate") are not sent again: they get an error answer. After MAX_RESTARTS starts in a
row without any answer from KataGo (it cannot start, for example), it is not started again, and the
waiting queries and the next ones get an error. Only close() stops KataGo for good. So every part of
KentoGo that uses KataGo (the quiz, the screens, the analysis of games) goes on after KataGo stopped.

KataGo can also hang without stopping (its GPU stops answering, for example). A watchdog thread looks
every CHECK_SECONDS: when an analysis has been waiting and KataGo has written no answer at all for
HANG_SECONDS (counted from the last answer, the sending of the oldest waiting analysis, and KataGo being
ready, whichever is the latest), KataGo is stopped and started again in the same way. Loading the model
does not count (it can take minutes the first time, with TensorRT): the time runs only once KataGo is
ready. A single analysis is never that long: the visits are set so that one analysis takes seconds (see
katago.presets), and KataGo answers the many queries of a game one after another.
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
from dataclasses import dataclass

from kentogo.katago.locate import EngineCommand

Callback = Callable[[dict], None]

# Number of lines of KataGo's error output that are kept for error messages.
STDERR_LINES_KEPT = 50
READY_MESSAGE = "ready to begin handling requests"  # KataGo writes this when it has started.
VERSION_QUERY = {"action": "query_version"}  # Answered as soon as KataGo is ready.
MAX_RESTARTS = 3  # KataGo is started again at most this many times in a row without an answer.
HANG_SECONDS = 120.0  # KataGo hangs when it writes nothing this long while an analysis waits (see the module).
CHECK_SECONDS = 5.0  # How often the watchdog looks.

# On Windows, a console program started from a program with a window opens a black console
# window of its own. This flag stops that. Other systems have no such flag (0 means none).
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _is_warning(answer: dict) -> bool:
    """True for KataGo's warning about a query, such as {"id": ..., "field": ..., "warning": ...}.

    A warning is not the answer: the analysis (or an error) for the same id comes after it.
    """
    return "warning" in answer and not any(key in answer for key in ("rootInfo", "moveInfos", "error"))


@dataclass
class _Waiting:
    """A query that waits for its final answer.

    Attributes:
        line: The query as it was written to KataGo (one JSON line, with its id).
        callback: Called with its answers.
        resendable: It can be sent again after KataGo was started again (an analysis, not a control action).
        analysis: It is an analysis (not a control action, which KataGo answers at once).
        sent_at: When it was last written to KataGo (time.monotonic).
    """

    line: str
    callback: Callback
    resendable: bool
    analysis: bool = False
    sent_at: float = 0.0


_Failed = tuple[str, Callback, str]  # A query that gets an error answer: its id, its callback and the message.


class KataGoProcess:
    """One running KataGo analysis engine, started again when it stops by itself (see the module).

    Several queries can be sent at the same time. KataGo is started by start(),
    and must be stopped with close() when it is no longer needed.
    """

    def __init__(
        self, command: EngineCommand, hang_seconds: float = HANG_SECONDS, check_seconds: float = CHECK_SECONDS
    ):
        """Prepare to run KataGo. It is not started yet.

        Args:
            command: How to start KataGo (see katago.locate.engine_command).
            hang_seconds: How long KataGo may write nothing while an analysis waits (see the module).
            check_seconds: How often the watchdog looks.
        """
        self.command = command
        self.hang_seconds = hang_seconds
        self.check_seconds = check_seconds
        self._process: subprocess.Popen | None = None
        self._waiting: dict[str, _Waiting] = {}
        self._lock = threading.RLock()
        self._ids = itertools.count(1)
        self._stderr: deque[str] = deque(maxlen=STDERR_LINES_KEPT)
        self._started_at = 0.0
        self._ready = threading.Event()  # Set when KataGo says that it is ready, or when its output ends.
        self._ready_seconds: float | None = None  # How long KataGo took to get ready.
        self._closed = False  # close() was called: KataGo is not started again.
        self._restarts = 0  # The starts in a row without an answer from KataGo.
        self._last_output = 0.0  # When KataGo last wrote an answer (time.monotonic).
        self._ready_at: float | None = None  # When the running KataGo got ready (None before).

    def start(self) -> None:
        """Start KataGo, and the background threads that read its output.

        Raises:
            OSError: If the program cannot be started.
        """
        self._started_at = time.monotonic()
        self._popen()
        try:
            self.query(VERSION_QUERY, self._answered_version)
        except (RuntimeError, OSError):  # KataGo stopped at once: _read_errors ends the waiting.
            pass
        threading.Thread(target=self._watch, name="katago-watchdog", daemon=True).start()

    def _popen(self) -> subprocess.Popen:
        """Start the KataGo program and the threads that read its output and error output (under the lock)."""
        command = self.command.command[0] if self.command.shell else list(self.command.command)
        with self._lock:
            self._ready_at = None
            self._process = process = subprocess.Popen(
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
        threading.Thread(target=self._read_answers, args=(process,), name="katago-stdout", daemon=True).start()
        threading.Thread(target=self._read_errors, args=(process,), name="katago-stderr", daemon=True).start()
        return process

    def query(self, request: dict, callback: Callback) -> str:
        """Send a query to KataGo (KataGo is started again first when it stopped by itself, see the module).

        Args:
            request: The query, without "id" (see KataGo's Analysis_Engine.md). Its "overrideSettings"
                is not sent when the settings are on the command line.
            callback: Called with each answer for this query, in the background thread.
                An answer with the key "error" means that the query failed.

        Returns:
            The id given to the query.

        Raises:
            RuntimeError: If KataGo was closed, was never started, or could not be started again.
            OSError: If KataGo could not be written to, even after it was started again.
        """
        query_id = f"kentogo-{next(self._ids)}"
        if self.command.settings_in_command:
            # The settings are on the command line (see locate.fixed_settings).
            request = {key: value for key, value in request.items() if key != "overrideSettings"}
        analysis = "action" not in request
        waiting = _Waiting(json.dumps({**request, "id": query_id}) + "\n", callback, analysis, analysis)
        failed: list[_Failed] = []
        try:
            with self._lock:
                failed += self._ensure_running()
                self._waiting[query_id] = waiting
                try:
                    self._write(waiting)
                except OSError:  # KataGo cannot be written to: start it again, which sends the query once more.
                    failed += self._restart("its input cannot be written")
                    if query_id not in self._waiting or self._process is None:
                        raise
        finally:
            _answer_errors(failed)
        return query_id

    def _ensure_running(self) -> list[_Failed]:
        """Start KataGo again when it stopped by itself (under the lock). Returns the queries to answer with an error.

        Raises:
            RuntimeError: If it was closed, never started, or could not be started again (MAX_RESTARTS).
        """
        if self._closed or (self._process is None and not self._started_at):
            raise RuntimeError("KataGo is not running")
        failed = self._restart("it had stopped") if self._process is None or self._process.poll() is not None else []
        if self._process is None:
            _answer_errors(failed)
            raise RuntimeError("KataGo is not running: " + self.error_output())
        return failed

    def _write(self, waiting: _Waiting) -> None:
        """Write a query to KataGo, and keep when (under the lock)."""
        waiting.sent_at = time.monotonic()
        self._process.stdin.write(waiting.line)
        self._process.stdin.flush()

    def _restart(self, reason: str) -> list[_Failed]:
        """Start KataGo again and send the waiting queries to it once more (under the lock; see the module).

        Without restarts left (MAX_RESTARTS in a row without an answer), KataGo is not started again.

        Returns:
            The queries to answer with an error, after the lock is released (their callbacks may send queries).
        """
        if self._closed:
            return []
        old = self._process
        if old is not None and old.poll() is None:
            old.kill()
        if self._restarts >= MAX_RESTARTS:
            self._process = None
            print(f"KataGo stopped ({reason}) and is not started again: it gave no answer", file=sys.stderr)
            return self._take_waiting("KataGo stopped and could not be started again: " + self.error_output())
        self._restarts += 1
        print(f"KataGo stopped ({reason}): starting it again ({self._restarts})", file=sys.stderr)
        try:
            self._popen()
        except OSError as error:
            self._process = None
            return self._take_waiting(f"KataGo could not be started again: {error}")
        failed = self._send_again()
        self._ask_version()
        return failed

    def _ask_version(self) -> None:
        """Send query_version to the new KataGo, so that it is known to be ready even without its log (under the lock)."""
        query_id = f"kentogo-{next(self._ids)}"
        waiting = _Waiting(json.dumps({**VERSION_QUERY, "id": query_id}) + "\n", self._answered_version, False)
        self._waiting[query_id] = waiting
        try:
            self._write(waiting)
        except OSError:  # It stopped at once: its output ends, and it is started again from there.
            pass

    def _send_again(self) -> list[_Failed]:
        """Send the waiting queries to the new KataGo, each only once (under the lock).

        Returns:
            The queries that are not sent again, to answer with an error.
        """
        message = "KataGo stopped: " + self.error_output()
        failed = []
        for query_id, waiting in list(self._waiting.items()):
            if waiting.resendable:
                waiting.resendable = False  # Sent again only once.
                try:
                    self._write(waiting)
                    continue
                except OSError:
                    pass
            failed.append((query_id, self._waiting.pop(query_id).callback, message))
        return failed

    def _take_waiting(self, message: str) -> list[_Failed]:
        """Forget all waiting queries (under the lock), and return them to answer with an error."""
        failed = [(query_id, waiting.callback, message) for query_id, waiting in self._waiting.items()]
        self._waiting.clear()
        return failed

    def terminate(self, query_id: str) -> None:
        """Ask KataGo to stop reading a query (KataGo's "terminate" action); nothing happens when it is not running.

        KataGo then gives the query its final answer at once, with the visits read so far (or none).
        """
        if not query_id or not self.is_running:
            return
        try:
            self.query({"action": "terminate", "terminateId": query_id}, lambda _answer: None)
        except (RuntimeError, OSError):  # KataGo stopped just now: the query has its error answer anyway.
            pass

    def terminate_all(self) -> None:
        """Ask KataGo to stop reading all queries (KataGo's "terminate_all" action); nothing happens without KataGo."""
        if not self.is_running:
            return
        try:
            self.query({"action": "terminate_all"}, lambda _answer: None)
        except (RuntimeError, OSError):  # KataGo stopped just now: the queries have their error answers anyway.
            pass

    def close(self) -> None:
        """Stop KataGo for good (it is not started again). Queries that are still waiting get an error answer."""
        with self._lock:
            self._closed = True
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

    @property
    def is_running(self) -> bool:
        """True while the KataGo process is running."""
        return self._process is not None and self._process.poll() is None

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

    def _read_answers(self, process: subprocess.Popen) -> None:
        """Read KataGo's answers and call the callbacks (runs in a background thread for one process).

        When the output ends or cannot be read, KataGo is started again (see the module), unless it was closed
        or another process has already taken its place.
        """
        reason = "its output ended"
        try:
            for line in process.stdout:
                self._answer(line)
        except (OSError, ValueError) as error:  # The output cannot be read (or was closed while being read).
            reason = f"its output cannot be read: {error}"
        process.wait()
        with self._lock:
            if self._process is not process:
                return  # Another process has taken its place (it was started again, or closed).
            failed = (
                self._take_waiting("KataGo stopped: " + self.error_output()) if self._closed else self._restart(reason)
            )
        _answer_errors(failed)

    def _answer(self, line: str) -> None:
        """Give one line of KataGo's output to the callback of its query."""
        try:
            answer = json.loads(line)
        except json.JSONDecodeError:
            return  # KataGo writes only JSON here, so this should not happen.
        if _is_warning(answer):
            # A warning about the query (for example an unknown field). The real answer still comes.
            print(f"KataGo warning: {answer}", file=sys.stderr)
            return
        self._restarts = 0  # KataGo answers: it can be started again after it stops.
        self._last_output = time.monotonic()
        callback = self._callback_for(answer)
        if callback is not None:
            try:
                callback(answer)
            except Exception:  # One broken callback must not stop the answers of all other queries.
                traceback.print_exc()

    def _callback_for(self, answer: dict) -> Callback | None:
        """Return the callback of the query that an answer belongs to.

        The callback is forgotten after the final answer. An answer with
        "isDuringSearch": true is not final, so more answers will come.
        """
        query_id = answer.get("id")
        with self._lock:
            waiting = self._waiting.get(query_id) if answer.get("isDuringSearch") else self._waiting.pop(query_id, None)
        return waiting.callback if waiting is not None else None

    def _read_errors(self, process: subprocess.Popen) -> None:
        """Keep the last lines of KataGo's error output (runs in a background thread).

        When KataGo says that it is ready, the time that it took to start is written to the
        console (or the log), as starting can take long (loading the model, preparing the GPU).
        """
        try:
            for line in process.stderr:
                self._stderr.append(line.rstrip())
                if READY_MESSAGE in line:
                    self._got_ready()
        except (OSError, ValueError):  # The error output cannot be read: the answers' thread sees it too.
            pass
        self._ready.set()  # KataGo has stopped: nobody should wait for it any more.

    def _answered_version(self, answer: dict) -> None:
        """Take the answer to query_version as the sign that KataGo is ready (an error answer means it stopped)."""
        if "error" not in answer:
            self._got_ready()

    def _got_ready(self) -> None:
        """Keep when KataGo got ready (and how long it took, the first time only), and end the waiting for it."""
        with self._lock:
            if self._ready_at is None:
                self._ready_at = time.monotonic()
        if self._ready_seconds is None:
            self._ready_seconds = time.monotonic() - self._started_at
            print(f"KataGo is ready ({self._ready_seconds:.1f} s after it was started)", file=sys.stderr)
        self._ready.set()

    def _watch(self) -> None:
        """Start KataGo again when it hangs (see the module); runs in a background thread until close()."""
        while not self._closed:
            time.sleep(self.check_seconds)
            with self._lock:
                failed = self._restart_if_hung()
            _answer_errors(failed)

    def _restart_if_hung(self) -> list[_Failed]:
        """Start KataGo again when it has hung (under the lock). Returns the queries to answer with an error."""
        if self._closed or self._process is None or self._ready_at is None:
            return []
        analyses = [waiting.sent_at for waiting in self._waiting.values() if waiting.analysis]
        if not analyses:
            return []
        quiet = time.monotonic() - max(self._last_output, min(analyses), self._ready_at)
        if quiet < self.hang_seconds:
            return []
        return self._restart(f"no answer for {quiet:.0f} s")

    def _fail_waiting_queries(self, message: str) -> None:
        """Give an error answer to every query that is still waiting."""
        with self._lock:
            failed = self._take_waiting(message)
        _answer_errors(failed)


def _answer_errors(failed: list[_Failed]) -> None:
    """Give each query its error answer (an error in a callback is printed, as for any answer)."""
    for query_id, callback, message in failed:
        try:
            callback({"id": query_id, "error": message})
        except Exception:
            traceback.print_exc()
