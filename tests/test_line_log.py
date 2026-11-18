"""Tests for kentogo.line_log (the log of the human-like moves of the user)."""

import json
from datetime import datetime

from kentogo.line_log import LINE_PREFIX, log_line

NOW = datetime(2026, 11, 18, 9, 30, 0)


def test_a_record_is_told_on_the_console_and_appended_to_the_file(tmp_path, capsys):
    """One JSON object on a line, with the time, both on stderr (after the prefix) and in the file."""
    path = tmp_path / "log" / "human_line.jsonl"
    log_line({"event": "human_best_move", "chosen": "D4"}, path, NOW)
    log_line({"event": "human_best_move", "chosen": "Q16"}, path, NOW)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["chosen"] for line in lines] == ["D4", "Q16"]
    assert json.loads(lines[0])["time"] == "2026-11-18T09:30:00"
    assert capsys.readouterr().err.splitlines()[0] == LINE_PREFIX + lines[0]


def test_a_log_file_that_cannot_be_written_is_told_and_the_quiz_goes_on(tmp_path, capsys):
    """A folder in place of the file: the error is told on stderr, nothing is raised."""
    path = tmp_path / "human_line.jsonl"
    path.mkdir()
    log_line({"event": "human_best_move"}, path, NOW)
    assert "cannot be written" in capsys.readouterr().err
