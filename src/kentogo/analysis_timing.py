"""How long the analysis of each game took, to check the speed of the analysis on the user's computer.

For each game that is analyzed (see analysis_run), one JSON object is told, on one line (JSON Lines),
so that a program can read it:

- on the console (stderr), after the prefix TIMING_PREFIX;
- appended to the log file LOG_PATH (~/.kentogo/analysis_timing.jsonl), when it can be written.

Its keys:

- "file": the file name; "finished": the local time it ended (ISO 8601); "outcome": "written" or "failed";
  "kentogo": KentoGo's version.
- "seconds": "total", "analysis" (KataGo's reading) and "writing" (the analysis put into the game, the
  backup and the file written).
- "steps": the steps of the analysis in their order (see analysis.analyze), each with its "step" name,
  its "seconds" (from the end of the step before it, or the start of the game) and its "answers" (the
  answers of KataGo it got).
- "nodes" (all nodes of the game), "problem_nodes" (the moves that can become problems), "deep_nodes"
  (the moves read deeply), "failed_nodes" (the nodes that KataGo could not analyze).
- "visits": "first" (each position of the first analysis) and "deep" (the deep reading).
- "bytes": the size of the file "before" and "after" (0 when it was not written).
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from kentogo.analysis.game_analysis import GameAnalysis
from kentogo.settings_file import SETTINGS_PATH

TIMING_PREFIX = "KENTOGO_ANALYSIS_TIMING "
LOG_PATH = SETTINGS_PATH.parent / "analysis_timing.jsonl"


@dataclass
class StepClock:
    """Times the steps of the analysis of one game, from its progress (see analysis.game_analysis.Progress).

    Attributes:
        clock: Gives the time in seconds (time.monotonic; tests give their own).
        started: When the game started.
        steps: For each step, in the order they came: the time of its last answer and the number of answers.
    """

    clock: Callable[[], float] = time.monotonic
    started: float = field(init=False)
    steps: dict[str, list[float]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.started = self.clock()

    def progress(self, step: str, _done: int, _total: int) -> None:
        """Keep the time of an answer of a step (called in KataGo's thread)."""
        now = self.clock()
        found = self.steps.setdefault(step, [now, 0])
        found[0] = now
        found[1] += 1

    def step_times(self) -> list[dict]:
        """Return each step with its seconds (from the end of the step before it) and its answers."""
        found, before = [], self.started
        for step, (end, answers) in self.steps.items():
            found.append({"step": step, "seconds": round(end - before, 2), "answers": int(answers)})
            before = end
        return found


@dataclass(frozen=True)
class GameTiming:
    """What is known about one game when it has been analyzed and written.

    Attributes:
        file: The file name.
        outcome: "written" or "failed".
        clock: The times of the steps.
        analyzed: When the analysis ended (the clock's time).
        ended: When the writing ended (the clock's time).
        game: The analysis.
        visits: The visits of the first analysis and of the deep reading.
        sizes: The size of the file before and after (0 when it was not written).
        version: KentoGo's version.
    """

    file: str
    outcome: str
    clock: StepClock
    analyzed: float
    ended: float
    game: GameAnalysis
    visits: tuple[int, int]
    sizes: tuple[int, int]
    version: str


def timing_record(timing: GameTiming, finished: datetime) -> dict:
    """Return the JSON object of a game (see the module's docstring)."""
    game, clock = timing.game, timing.clock
    return {
        "file": timing.file,
        "finished": finished.isoformat(timespec="seconds"),
        "outcome": timing.outcome,
        "kentogo": timing.version,
        "seconds": {
            "total": round(timing.ended - clock.started, 2),
            "analysis": round(timing.analyzed - clock.started, 2),
            "writing": round(timing.ended - timing.analyzed, 2),
        },
        "steps": clock.step_times(),
        "nodes": len(game.nodes),
        "problem_nodes": len(game.problem_nodes),
        "deep_nodes": len(game.deep_nodes),
        "failed_nodes": game.failed,
        "visits": {"first": timing.visits[0], "deep": timing.visits[1]},
        "bytes": {"before": timing.sizes[0], "after": timing.sizes[1]},
    }


def log_timing(record: dict, log_path: Path | None = None) -> None:
    """Tell the record on the console and append it to the log file (LOG_PATH unless another is given).

    A log file that cannot be written is told; the analysis goes on.
    """
    line = json.dumps(record, ensure_ascii=False)
    print(TIMING_PREFIX + line, file=sys.stderr)
    path = (log_path or LOG_PATH).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(line + "\n")
    except OSError as error:
        print(f"KentoGo: the analysis timing log cannot be written: {error}", file=sys.stderr)
