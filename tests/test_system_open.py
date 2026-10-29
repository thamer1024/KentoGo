"""Tests for kentogo.system_open."""

from pathlib import Path

from kentogo.system_open import open_command

FILE = Path("prompt.txt")


def test_open_command():
    """macOS opens text files in the text editor, Linux uses xdg-open, and Windows uses os.startfile."""
    assert open_command(FILE, "darwin") == ["open", "-t", "prompt.txt"]
    assert open_command(FILE, "linux") == ["xdg-open", "prompt.txt"]
    assert open_command(FILE, "win32") is None
