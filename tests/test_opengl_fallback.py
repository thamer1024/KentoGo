"""Tests for kentogo.opengl_fallback."""

import sys

import pytest

from kentogo import opengl_fallback
from kentogo.opengl_fallback import (
    ANGLE_BACKEND,
    PYINSTALLER_RESET,
    OldOpenGLError,
    command_to_run_again,
    install_check,
    start_again_with_angle,
)


@pytest.fixture(autouse=True)
def no_hook(monkeypatch):
    """Each test starts without Kivy's hook, and it is removed after the test."""
    monkeypatch.delattr(sys, "_kivy_opengl_required_func", raising=False)


def test_the_check_is_only_on_windows_without_a_chosen_backend():
    """Only Windows needs it, and a chosen backend (such as ANGLE after starting again) is kept."""
    assert not install_check("darwin", {})
    assert not install_check("win32", {"KIVY_GL_BACKEND": ANGLE_BACKEND})
    assert not hasattr(sys, "_kivy_opengl_required_func")
    assert install_check("win32", {})


def test_an_old_opengl_raises_instead_of_stopping():
    """Kivy's hook raises OldOpenGLError, which tells the version that was found."""
    install_check("win32", {})
    with pytest.raises(OldOpenGLError, match="OpenGL 1.1"):
        sys._kivy_opengl_required_func(1, 1, b"1.1.0", b"Microsoft Corporation", b"GDI Generic")


def test_the_command_to_start_again():
    """KentoGo.exe is started again as it is; from the source, the module is run with Python."""
    assert command_to_run_again(True, "C:/KentoGo/KentoGo.exe", ["C:/KentoGo/KentoGo.exe", "games"]) == [
        "C:/KentoGo/KentoGo.exe",
        "games",
    ]
    assert command_to_run_again(False, "python", ["kentogo", "--no-katago"]) == [
        "python",
        "-m",
        "kentogo.app",
        "--no-katago",
    ]


def test_started_again_with_angle(monkeypatch):
    """KentoGo is started again with the same arguments and KIVY_GL_BACKEND set to ANGLE."""
    started = []
    monkeypatch.setattr(sys, "argv", ["kentogo", "games"])
    monkeypatch.setattr(opengl_fallback.sys, "frozen", False, raising=False)
    start_again_with_angle(lambda command, env: started.append((command, env)))
    command, env = started[0]
    assert command[1:] == ["-m", "kentogo.app", "games"] and env["KIVY_GL_BACKEND"] == ANGLE_BACKEND


def test_the_program_in_one_file_unpacks_itself_again(monkeypatch):
    """KentoGo.exe in one file is started as a new program, not with the files of the one that ends."""
    started = []
    monkeypatch.setattr(sys, "argv", ["C:/KentoGo.exe"])
    monkeypatch.setattr(opengl_fallback.sys, "frozen", True, raising=False)
    start_again_with_angle(lambda command, env: started.append((command, env)))
    assert started[0][1][PYINSTALLER_RESET] == "1"
