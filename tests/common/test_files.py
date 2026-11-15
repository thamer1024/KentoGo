"""Tests for kentogo.common.files."""

import os

from kentogo.common.files import newest_first


def test_newest_first(tmp_path):
    """The most recently changed file comes first, files changed at the same time by name, a missing file last."""
    for name, seconds in (("old.sgf", 100), ("b.sgf", 300), ("a.sgf", 300), ("new.sgf", 500)):
        path = tmp_path / name
        path.write_text("(;)", encoding="utf-8")
        os.utime(path, (seconds, seconds))
    paths = [tmp_path / name for name in ("old.sgf", "gone.sgf", "b.sgf", "new.sgf", "a.sgf")]
    assert [path.name for path in newest_first(paths)] == ["new.sgf", "a.sgf", "b.sgf", "old.sgf", "gone.sgf"]
