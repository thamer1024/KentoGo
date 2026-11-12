"""Helpers of the tests that start the fake KataGo (katago/fake_katago.py) as a real KataGo program."""

import sys
from pathlib import Path

from kentogo.katago.engine_settings import EngineSettings

FAKE_KATAGO = Path(__file__).parent / "katago" / "fake_katago.py"


def make_fake_katago(folder: Path) -> Path:
    """Make a program that starts the fake KataGo (fake_katago.py) with this Python.

    On Windows it is a .cmd file, and on macOS and Linux a shell script, so that it can be
    started like a real KataGo program on each system.
    """
    if sys.platform == "win32":
        katago = folder / "katago.cmd"
        katago.write_text(f'@"{sys.executable}" "{FAKE_KATAGO}" %*\n', encoding="utf-8")
    else:
        katago = folder / "katago"
        katago.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_KATAGO}" "$@"\n', encoding="utf-8")
        katago.chmod(0o755)
    return katago


def fake_katago_settings(tmp_path, **values) -> EngineSettings:
    """Make engine settings that start the fake KataGo, with existing model and settings files."""
    for name in ("model.bin.gz", "analysis.cfg"):
        (tmp_path / name).write_text("x")
    katago = make_fake_katago(tmp_path)
    return EngineSettings(
        katago=str(katago), model=str(tmp_path / "model.bin.gz"), config=str(tmp_path / "analysis.cfg"), **values
    )
