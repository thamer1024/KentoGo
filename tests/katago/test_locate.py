"""Tests for kentogo.katago.locate."""

import json
import os
from pathlib import Path

import pytest

from kentogo.katago.locate import (
    EngineCommand,
    KataGoNotFoundError,
    engine_command,
    find_katrain_package,
    fixed_settings,
    katrain_package,
    read_engine_config,
    resolve_path,
)


@pytest.fixture
def files(tmp_path):
    """Make fake KataGo, model and settings files, like a Homebrew installation."""
    paths = {name: tmp_path / name for name in ("katago", "model.bin.gz", "human.bin.gz", "analysis.cfg")}
    for path in paths.values():
        path.write_text("x")
    return paths


def engine(files, **changes) -> dict:
    """Make engine settings like the ones in KaTrain's config.json."""
    settings = {
        "backend": "local",
        "katago": str(files["katago"]),
        "altcommand": "",
        "remote_url": "",
        "model": str(files["model.bin.gz"]),
        "humanlike_model": "",
        "config": str(files["analysis.cfg"]),
        "max_visits": 2500,
    }
    settings.update(changes)
    return settings


def no_program(_name):
    """A fake shutil.which that finds nothing."""
    return None


def test_read_engine_config(tmp_path):
    """The engine part of KaTrain's config.json is read."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"engine": {"max_visits": 100}, "general": {}}), encoding="utf-8")
    assert read_engine_config(path) == {"max_visits": 100}


@pytest.mark.parametrize("text", ["{broken", '{"general": {}}'])
def test_read_broken_engine_config(tmp_path, text):
    """A broken file, or a file without engine settings, is an error."""
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(KataGoNotFoundError):
        read_engine_config(path)


def test_command_is_the_same_as_katrain(files):
    """The command has the same arguments as KaTrain's command."""
    command = engine_command(engine(files), which=no_program)
    assert command.command == (
        str(files["katago"]),
        "analysis",
        "-model",
        str(files["model.bin.gz"]),
        "-config",
        str(files["analysis.cfg"]),
        "-override-config",
        f"homeDataDir={os.path.expanduser('~/.katrain')}",
    )
    assert (command.shell, command.max_visits) == (False, 2500)


def test_fixed_settings_go_to_the_command_line(files):
    """The settings of every query are added to -override-config, and queries are told not to send them."""
    command = fixed_settings(engine_command(engine(files), which=no_program), {"reportAnalysisWinratesAs": "BLACK"})
    home = os.path.expanduser("~/.katrain")
    assert command.command[-1] == f"homeDataDir={home},reportAnalysisWinratesAs=BLACK"
    assert command.settings_in_command
    custom = EngineCommand(("my katago",), True, 10)
    assert fixed_settings(custom, {"a": 1}) == custom  # A user's own command line is not changed.


def test_command_with_human_model(files):
    """A human-like model is given to KataGo with -human-model."""
    command = engine_command(engine(files, humanlike_model=str(files["human.bin.gz"])), which=no_program)
    assert command.command[4:6] == ("-human-model", str(files["human.bin.gz"]))


def test_katago_from_the_path(files):
    """An empty KataGo setting, or a program name, means KataGo in the PATH."""
    found = {"katago": "bin/katago"}.get
    expected = str(Path("bin/katago"))  # With "\\" on Windows.
    assert engine_command(engine(files, katago=""), which=found).command[0] == expected
    assert engine_command(engine(files, katago="katago"), which=found).command[0] == expected
    with pytest.raises(KataGoNotFoundError):
        engine_command(engine(files, katago=""), which=no_program)


def test_paths_inside_katrain(tmp_path, files):
    """Paths that start with "katrain/" are inside the KaTrain program folder."""
    package = tmp_path / "package"
    (package / "KataGo").mkdir(parents=True)
    (package / "KataGo" / "katago-osx").write_text("x")
    (package / "models").mkdir()
    (package / "models" / "m.bin.gz").write_text("x")
    settings = engine(files, katago="", model="katrain/models/m.bin.gz")
    command = engine_command(settings, katrain_package=package, which=no_program)
    assert command.command[0] == str(package / "KataGo" / "katago-osx")
    assert command.command[3] == str(package / "models" / "m.bin.gz")


def test_path_inside_katrain_without_the_folder():
    """A path inside KaTrain cannot be used if the KaTrain folder is not given."""
    with pytest.raises(KataGoNotFoundError):
        resolve_path("katrain/models/m.bin.gz", None)


def test_missing_files(files):
    """A missing or empty setting for KataGo, the model or the settings file is an error."""
    for key in ("katago", "model", "config"):
        with pytest.raises(KataGoNotFoundError):
            engine_command(engine(files, **{key: "/not/here"}), which=no_program)
    with pytest.raises(KataGoNotFoundError):
        engine_command(engine(files, model=""), which=no_program)


def test_custom_and_remote_engines(files):
    """KaTrain's custom command is used as it is, and a remote engine is not supported."""
    command = engine_command(engine(files, backend="custom", altcommand="mykatago analysis"), which=no_program)
    assert (command.command, command.shell) == (("mykatago analysis",), True)
    with pytest.raises(KataGoNotFoundError):
        engine_command(engine(files, backend="remote"), which=no_program)


def test_windows_path_of_katago(files):
    """A KataGo path written with "\\" (as on Windows) is a path, not a program name to look for in the PATH."""
    windows_style = str(files["katago"]).replace("/", "\\")
    command = engine_command(engine(files, katago=windows_style), which=no_program)
    assert Path(command.command[0]) == files["katago"]


def make_katrain(folder: Path) -> Path:
    """Make a fake "katrain" folder of the KaTrain program, with its KataGo folder."""
    (folder / "KataGo").mkdir(parents=True)
    return folder


def test_katrain_folder_from_the_settings(tmp_path):
    """The folder in the settings can be the "katrain" folder, or a folder that has it inside."""
    package = make_katrain(tmp_path / "KaTrain" / "katrain")
    assert katrain_package(str(package)) == package
    assert katrain_package(str(tmp_path / "KaTrain")) == package
    bundled = make_katrain(tmp_path / "Bundle" / "_internal" / "katrain")  # A program made with PyInstaller.
    assert katrain_package(str(tmp_path / "Bundle")) == bundled
    assert katrain_package(str(tmp_path / "nothing")) is None


def test_katrain_folder_found_automatically(tmp_path):
    """An empty setting looks in the usual places, and takes the first one that looks like KaTrain's."""
    empty = tmp_path / "empty"
    empty.mkdir()
    package = make_katrain(tmp_path / "found")
    assert katrain_package("", candidates=[empty, tmp_path / "missing", package]) == package
    assert find_katrain_package([empty]) is None
