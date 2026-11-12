"""Tests for kentogo.analysis_timing (how long the analysis of each game took, told and kept as JSON Lines)."""

import json
from datetime import datetime

from pysgf import GoGame

from kentogo import analysis_timing
from kentogo.analysis.game_analysis import GameAnalysis
from kentogo.analysis_timing import TIMING_PREFIX, GameTiming, StepClock, log_timing, timing_record


class Ticks:
    """A clock that goes on by the given seconds each time it is read."""

    def __init__(self, *steps):
        self.now, self.steps = 100.0, list(steps)

    def __call__(self):
        self.now += self.steps.pop(0) if self.steps else 0.0
        return self.now


def test_each_step_takes_the_time_since_the_step_before_it():
    """The seconds of a step run from the end of the step before it (or the start); its answers are counted."""
    clock = StepClock(Ticks(0.0, 1.0, 2.0, 3.0))  # Started at 100; answers at 101, 103 (first), 106 (deep).
    clock.progress("first", 1, 2)
    clock.progress("first", 2, 2)
    clock.progress("deep", 1, 1)
    assert clock.step_times() == [
        {"step": "first", "seconds": 3.0, "answers": 2},
        {"step": "deep", "seconds": 3.0, "answers": 1},
    ]


def test_the_record_of_a_game():
    """The record has the file, the seconds of the whole, of KataGo and of the writing, the nodes and the sizes."""
    clock = StepClock(Ticks(0.0, 4.0))
    clock.progress("first", 1, 1)
    game = GameAnalysis(GoGame.parse_sgf("(;SZ[5];B[cc];W[bb])"))
    timing = GameTiming("a.sgf", "written", clock, 104.0, 105.5, game, (500, 2000), (900, 300), "1.2.3")
    record = timing_record(timing, datetime(2026, 11, 12, 21, 50, 0))
    assert record["file"] == "a.sgf" and record["finished"] == "2026-11-12T21:50:00"
    assert record["seconds"] == {"total": 5.5, "analysis": 4.0, "writing": 1.5}
    assert record["steps"] == [{"step": "first", "seconds": 4.0, "answers": 1}]
    assert (record["nodes"], record["problem_nodes"], record["deep_nodes"], record["failed_nodes"]) == (3, 0, 0, 0)
    assert record["visits"] == {"first": 500, "deep": 2000} and record["bytes"] == {"before": 900, "after": 300}


def test_the_record_is_told_and_appended_as_one_json_line(tmp_path, capsys):
    """Each record is one line of JSON on the console (after the prefix) and in the log file."""
    log = tmp_path / "logs" / "timing.jsonl"
    log_timing({"file": "a.sgf", "seconds": {"total": 1.0}}, log)
    log_timing({"file": "b.sgf", "seconds": {"total": 2.0}}, log)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["file"] for line in lines] == ["a.sgf", "b.sgf"]
    told = [line for line in capsys.readouterr().err.splitlines() if line.startswith(TIMING_PREFIX)]
    assert json.loads(told[0][len(TIMING_PREFIX) :]) == {"file": "a.sgf", "seconds": {"total": 1.0}}


def test_the_log_goes_to_log_path_by_default():
    """Without a path, the log is LOG_PATH (the tests make it a file of their own folder, see conftest)."""
    log_timing({"file": "c.sgf"})
    assert json.loads(analysis_timing.LOG_PATH.read_text(encoding="utf-8"))["file"] == "c.sgf"
