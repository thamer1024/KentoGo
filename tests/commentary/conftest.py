"""Fixtures shared by the tests of the AI commentary."""

import os

import pytest


@pytest.fixture
def games(tmp_path):
    """A games folder, with a function that writes a game into it with a given time of change."""
    folder = tmp_path / "games"
    folder.mkdir()

    def write(name: str, text: str, modified_ns: int = 2_000):
        path = folder / name
        path.write_text(text, encoding="utf-8")
        os.utime(path, ns=(modified_ns, modified_ns))
        return path

    write.folder = folder
    return write
