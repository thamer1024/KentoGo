"""Tests for the settings of the programs made with PyInstaller (packaging/*/kentogo.spec)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "kentogo"
SPECS = [ROOT / "packaging" / system / "kentogo.spec" for system in ("windows", "macos")]


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda path: path.parent.name)
def test_every_data_file_is_in_the_program(spec_path):
    """Each folder of KentoGo with files that are not Python is put into the program, and the start is found.

    A version.txt made by hand next to the modules (see kentogo/version.py) is not one of them.
    """
    spec = spec_path.read_text(encoding="utf-8")
    folders = {
        path.parent.relative_to(PACKAGE).parts[0]
        for path in PACKAGE.rglob("*")
        if path.is_file()
        and path.parent != PACKAGE
        and path.suffix not in (".py", ".pyc")
        and "__pycache__" not in path.parts
    }
    assert folders
    for folder in folders:
        assert f'"kentogo/{folder}"' in spec, f"src/kentogo/{folder} is not in {spec_path.name}"
    assert (spec_path.parent.parent / "kentogo_entry.py").is_file() and '"kentogo_entry.py"' in spec


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda path: path.parent.name)
def test_every_prompt_file_is_in_the_program(spec_path):
    """Each default prompt of the AI commentary (one for each language of the prompt) is put into the program."""
    spec = spec_path.read_text(encoding="utf-8")
    prompts = sorted((PACKAGE / "commentary").glob("*.txt"))
    assert len(prompts) == 2
    for path in prompts:
        assert f'"{path.name}"' in spec, f"{path.name} is not in {spec_path.name}"


@pytest.mark.parametrize(("system", "icon"), [("windows", "kentogo.ico"), ("macos", "kentogo.icns")])
def test_the_program_has_its_icon(system, icon):
    """Each program uses the icon made by tools/make_icon.py, in the format of its system."""
    spec = (ROOT / "packaging" / system / "kentogo.spec").read_text(encoding="utf-8")
    assert f'"{icon}"' in spec and (ROOT / "packaging" / "icons" / icon).is_file()


def test_the_window_has_the_icon():
    """The window (and the task bar or the Dock) shows the icon of the program."""
    from kentogo.gui import theme

    assert theme.APP_ICON.is_file() and theme.APP_ICON.parent == PACKAGE / "images"


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda path: path.parent.name)
def test_the_version_of_a_release_is_in_the_program(spec_path):
    """The file with the version is put where kentogo.version looks for it, when the workflow has written it."""
    spec = spec_path.read_text(encoding="utf-8")
    assert 'VERSION_FILE = ROOT / "packaging" / "version.txt"' in spec
    assert 'DATA.append((VERSION_FILE, "kentogo"))' in spec


def _release_version():
    """Load packaging/release_version.py (the folder packaging is not a Python package)."""
    path = ROOT / "packaging" / "release_version.py"
    spec = importlib.util.spec_from_file_location("release_version", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("commit_date", "version"),
    [
        ("2026-10-29T01:01:00+09:00", "1.1.0"),
        ("2026-10-29T01:02:00+09:00", "1.2.0"),
        ("2026-10-29T13:37:05+09:00", "13.37.5"),
        ("2026-10-29T00:00:00+09:00", "0.0.0"),
        ("2026-10-28T16:02:00+00:00", "16.2.0"),  # The time zone written in the commit is used.
    ],
)
def test_the_version_of_a_release_is_the_time_of_the_commit(commit_date, version):
    """The hour, the minute and the second of the commit are the version, without leading zeros."""
    assert _release_version().version_of(commit_date) == version


WINDOWS_SPEC = ROOT / "packaging" / "windows" / "kentogo.spec"


def test_windows_makes_the_program_in_one_file_and_as_a_folder():
    """KentoGo.exe is made as one file and as a folder, with the same files and the same version (as KaTrain)."""
    spec = WINDOWS_SPEC.read_text(encoding="utf-8")
    assert "coll = COLLECT(" in spec and "one_file = EXE(" in spec
    one_file = spec.split("one_file = EXE(")[1]
    assert all(part in one_file for part in ("a.binaries", "a.datas", "*DLLS", "version=VERSION_INFO"))
    assert spec.count("version=VERSION_INFO") == 2 and spec.count("upx=False") == 3


def _version_info():
    """Load packaging/windows/version_info.py (the folder packaging is not a Python package)."""
    path = ROOT / "packaging" / "windows" / "version_info.py"
    spec = importlib.util.spec_from_file_location("version_info", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("version", "numbers"),
    [("1.3.2", (1, 3, 2, 0)), ("13.37.5", (13, 37, 5, 0)), ("0.0.0", (0, 0, 0, 0)), ("1.2.3.4.5", (1, 2, 3, 4))],
)
def test_the_version_of_windows_has_four_numbers(version, numbers):
    """The version of a release gets 0 as the fourth number of Windows."""
    assert _version_info().version_numbers(version) == numbers


def test_the_version_information_of_the_exe():
    """The properties of KentoGo.exe show its name and its version.

    Only where the program is made: PyInstaller makes the version information with pefile, which it
    installs only on Windows.
    """
    pytest.importorskip("PyInstaller.utils.win32.versioninfo")
    info = _version_info().version_info("1.3.2")
    assert (info.ffi.fileVersionMS, info.ffi.fileVersionLS) == ((1 << 16) | 3, 2 << 16)
    texts = {item.name: item.val for item in info.kids[0].kids[0].kids}
    assert texts["ProductVersion"] == "1.3.2" and texts["OriginalFilename"] == "KentoGo.exe"
