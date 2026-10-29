"""Start KentoGo again with ANGLE on Windows when the computer has only an old OpenGL.

Kivy needs OpenGL 2.0. A Windows computer without a graphics driver (an old PC, a virtual
machine, or a computer that only has Windows' own driver) has only OpenGL 1.1, and Kivy
stops with an error when it opens the window. Kivy on Windows comes with ANGLE, which draws
with DirectX instead of OpenGL, and works on such computers too.

So, before the window is opened, Kivy is told to raise OldOpenGLError instead of stopping
(Kivy calls sys._kivy_opengl_required_func when it is set). KentoGo then starts again with
KIVY_GL_BACKEND=angle_sdl2, and this one ends at once (its window, which Kivy could not
finish, is closed with it). This is done only when KIVY_GL_BACKEND is not set, so that a
KentoGo started again with ANGLE (or a user's own choice of backend) shows Kivy's own error
if it fails too.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence

ANGLE_BACKEND = "angle_sdl2"  # Kivy's backend that draws with DirectX (Windows only).
# Tells KentoGo.exe made as one file to unpack itself again: the KentoGo started again outlives this
# one, whose unpacked files are removed when it ends (PyInstaller ignores it in other programs).
PYINSTALLER_RESET = "PYINSTALLER_RESET_ENVIRONMENT"


class OldOpenGLError(Exception):
    """The computer's OpenGL is older than the one Kivy needs."""


def install_check(platform: str = sys.platform, environment: dict[str, str] | None = None) -> bool:
    """Make Kivy raise OldOpenGLError for an old OpenGL, on Windows when no backend is chosen.

    Call it before Kivy's window is made.

    Args:
        platform: The system (sys.platform; tests give another one).
        environment: The environment variables (os.environ by default).

    Returns:
        True if the check was installed.
    """
    environment = os.environ if environment is None else environment
    if platform != "win32" or environment.get("KIVY_GL_BACKEND"):
        return False
    sys._kivy_opengl_required_func = _raise_old_opengl  # Kivy's hook (see kivy.core.gl).
    return True


def start_again_with_angle(start: Callable[..., object] = subprocess.Popen) -> None:
    """Start KentoGo again with the same arguments and ANGLE (this KentoGo should end after this).

    Args:
        start: Starts a command without waiting for it (tests give a fake one).
    """
    print("OpenGL 2.0 is not found: KentoGo is started again with ANGLE (DirectX)", file=sys.stderr)
    command = command_to_run_again(getattr(sys, "frozen", False), sys.executable, sys.argv)
    start(command, env={**os.environ, "KIVY_GL_BACKEND": ANGLE_BACKEND, PYINSTALLER_RESET: "1"})


def command_to_run_again(frozen: bool, executable: str, argv: Sequence[str]) -> list[str]:
    """Return the command that starts KentoGo again with the same arguments.

    Args:
        frozen: True for the program made with PyInstaller (KentoGo.exe), False when run from the source.
        executable: sys.executable: KentoGo.exe itself, or Python.
        argv: sys.argv (its first item is the program, and is not passed again).
    """
    if frozen:
        return [executable, *argv[1:]]
    return [executable, "-m", "kentogo.app", *argv[1:]]


def _raise_old_opengl(major: int, minor: int, version, vendor, renderer) -> None:
    """Kivy's hook for an old OpenGL: raise OldOpenGLError instead of stopping the program."""
    raise OldOpenGLError(f"OpenGL {major}.{minor} ({vendor!r}, {renderer!r}, {version!r})")
