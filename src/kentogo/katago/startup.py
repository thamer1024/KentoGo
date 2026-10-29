"""Follow the loading of KataGo at the start of the app, and tell how long it may still take.

KataGo is started with the app (see app.open_engines): first the main model, then the
comparison model when the main one is ready. Loading a model takes from a few seconds to some
tens of seconds (the first start of the Metal or the OpenCL version also tunes itself for the
GPU), and KataGo does not tell how far it is. So the time that each KataGo took to get ready
is kept in a file (StartTimes), for each command line, and the next start shows how much of
that time is left. A command line that has not been started before shows only the time that
has passed.

Loading follows the stages one after the other; the screen asks it for the state now and then
(see gui.loading_dialog).
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

TIMES_FILE = "katago_start_times.json"  # In the settings folder (~/.kentogo).


class StartTimes:
    """The seconds that KataGo took to get ready, for each command line, kept in a file."""

    def __init__(self, path: Path | None):
        """Read the file.

        Args:
            path: The file, or None to keep nothing (tests, or no settings folder). It may start
                with "~" (the home folder).
        """
        self.path = path.expanduser() if path is not None else None
        self._seconds = _read_times(self.path)

    def expected(self, key: str) -> float | None:
        """Return the seconds that the command line took last time, or None if it was not started before."""
        return self._seconds.get(key)

    def remember(self, key: str, seconds: float) -> None:
        """Keep the seconds that the command line took now (the file is written at once)."""
        self._seconds[key] = round(seconds, 1)
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._seconds, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as error:  # Only the next estimate is lost.
            print(f"cannot keep KataGo's loading time: {error}", file=sys.stderr)


def _read_times(path: Path | None) -> dict[str, float]:
    """Read the kept seconds (an empty dict when there is no file, or it cannot be read)."""
    if path is None or not path.exists():
        return {}
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(values, dict):
        return {}
    return {key: float(value) for key, value in values.items() if isinstance(value, (int, float))}


@dataclass(frozen=True)
class LoadingStage:
    """One KataGo to wait for.

    Attributes:
        text_key: The text that tells what is loaded ("loading_main" or "loading_compare").
        key: KataGo's command line (its loading time is kept for it).
        is_ready: Returns True when KataGo is ready.
        has_failed: Returns True when KataGo will not get ready (it could not start, or it stopped).
        seconds: Returns how long KataGo took to get ready (None before it is ready).
    """

    text_key: str
    key: str
    is_ready: Callable[[], bool]
    has_failed: Callable[[], bool]
    seconds: Callable[[], float | None]


@dataclass(frozen=True)
class LoadingState:
    """What is loaded now.

    Attributes:
        text_key: The text that tells what is loaded.
        elapsed: The seconds since this KataGo began to load.
        expected: The seconds it took last time, or None if it was not started before.
    """

    text_key: str
    elapsed: float
    expected: float | None

    @property
    def remaining(self) -> float | None:
        """The seconds that are probably left, or None when it cannot be told (no time kept, or more has passed)."""
        if self.expected is None or self.elapsed >= self.expected:
            return None
        return self.expected - self.elapsed


class Loading:
    """Follows the stages of the loading, one after the other."""

    def __init__(self, stages: Sequence[LoadingStage], times: StartTimes, clock: Callable[[], float] = time.monotonic):
        """Begin with the first stage.

        Args:
            stages: The KataGo processes to wait for, in the order they are started.
            times: Where the loading times are kept.
            clock: Returns the time in seconds (tests give a fake one).
        """
        self._stages = list(stages)
        self._times = times
        self._clock = clock
        self._index = 0
        self._started_at = clock()

    def update(self) -> LoadingState | None:
        """Go on to the next stages that are ready or failed, and return the state now (None when all are done).

        The loading time of each KataGo that got ready is kept for the next start.
        """
        while self._index < len(self._stages):
            stage = self._stages[self._index]
            if stage.is_ready():
                seconds = stage.seconds()
                if seconds is not None:
                    self._times.remember(stage.key, seconds)
            elif not stage.has_failed():
                return LoadingState(stage.text_key, self._clock() - self._started_at, self._times.expected(stage.key))
            self._index += 1
            self._started_at = self._clock()
        return None
