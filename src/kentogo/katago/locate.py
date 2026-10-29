"""Find KataGo, its model and its settings file, in the same way as KaTrain.

KentoGo uses the KataGo that the user set up in KaTrain. KaTrain keeps its
settings in ~/.katrain/config.json, and the "engine" part of it says where
KataGo, the model and KataGo's analysis settings file are.

A path that starts with "katrain/" is inside the KaTrain program itself
(for example, the KataGo that comes with KaTrain). Such a path is found in the
"katrain" folder of the KaTrain program: the one set on the settings screen, or
one found in the usual places (see find_katrain_package). KaTrain's default
settings on Windows use such paths.

This module and process.py are the only places where the operating systems differ.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KATRAIN_CONFIG = Path("~/.katrain/config.json")
KATRAIN_DATA_FOLDER = "~/.katrain"
# What a "katrain" folder of the KaTrain program has inside (one of them is enough).
KATRAIN_PACKAGE_MARKS = ("KataGo", "models")


class KataGoNotFoundError(Exception):
    """Raised when KataGo, its model or its settings file cannot be found or used."""


@dataclass(frozen=True)
class EngineCommand:
    """How to start KataGo.

    Attributes:
        command: The program and its arguments. With shell=True it is one command line.
        shell: True if the command is a command line for the shell (KaTrain's "custom" engine).
        max_visits: How many positions KataGo reads for one analysis, as set in KaTrain.
        settings_in_command: True if the settings that queries usually send in "overrideSettings"
            are given on the command line instead, so queries must not send them (see fixed_settings).
    """

    command: tuple[str, ...]
    shell: bool
    max_visits: int
    settings_in_command: bool = False


def fixed_settings(command: EngineCommand, settings: dict) -> EngineCommand:
    """Give KataGo the settings of every query on the command line, so that queries need not send them.

    When a query sends "overrideSettings", KataGo checks its whole settings file again, and
    a warning becomes an error of the query. For example, a settings file made for the
    human-like model has humanSLProfile, which a normal model does not use, so every query
    to a normal model with that file fails. With the settings on the command line, the
    warning is only printed once when KataGo starts.

    Args:
        command: The command made by engine_command.
        settings: The settings, such as {"reportAnalysisWinratesAs": "BLACK"}.

    Returns:
        The new command, or the same command for a command line of the user's own
        ("custom" engine), which cannot be changed.
    """
    if command.shell or "-override-config" not in command.command:
        return command
    arguments = list(command.command)
    index = arguments.index("-override-config") + 1
    arguments[index] = ",".join([arguments[index], *(f"{key}={value}" for key, value in settings.items())])
    return EngineCommand(tuple(arguments), command.shell, command.max_visits, settings_in_command=True)


def read_engine_config(path: str | Path = DEFAULT_KATRAIN_CONFIG) -> dict:
    """Read the "engine" part of KaTrain's config.json.

    Args:
        path: Path of KaTrain's config.json.

    Returns:
        The engine settings.

    Raises:
        KataGoNotFoundError: If the file cannot be read or has no engine settings.
    """
    path = Path(path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KataGoNotFoundError(f"cannot read KaTrain's settings {path}: {error}") from error
    engine = data.get("engine") if isinstance(data, dict) else None
    if not isinstance(engine, dict):
        raise KataGoNotFoundError(f"KaTrain's settings {path} have no engine part")
    return engine


def resolve_path(text: str, katrain_package: Path | None) -> Path:
    """Turn a path written in KaTrain's settings into a full path, as KaTrain does.

    Args:
        text: The path. "~" means the home folder.
        katrain_package: The folder of the KaTrain program, used for paths that start with "katrain/".

    Returns:
        The full path.

    Raises:
        KataGoNotFoundError: If the path is inside KaTrain but katrain_package is not given.
    """
    text = text.strip().replace("\\", "/")
    if text.startswith("katrain/"):
        if katrain_package is None:
            raise KataGoNotFoundError(
                f"{text} is inside the KaTrain program; set KaTrain's program folder on the settings screen"
            )
        return katrain_package / text.removeprefix("katrain/")
    return Path(text).expanduser().absolute()


def engine_command(
    engine: dict,
    katrain_package: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> EngineCommand:
    """Make the command that starts KataGo, from KaTrain's engine settings.

    The command is the same as the one KaTrain uses (KaTrain 1.20.0, KataGoEngine).

    Args:
        engine: The engine settings (see read_engine_config).
        katrain_package: The folder of the KaTrain program, for paths that start with "katrain/".
        which: Finds a program in the PATH. Tests pass a fake one.

    Returns:
        The command.

    Raises:
        KataGoNotFoundError: If a file is missing, or KaTrain uses a remote engine.
    """
    max_visits = int(engine.get("max_visits", 500))
    backend = _backend(engine)
    if backend == "remote":
        raise KataGoNotFoundError("KaTrain uses a remote engine, which KentoGo does not support")
    elif backend == "custom":
        return EngineCommand((engine["altcommand"].strip(),), True, max_visits)

    katago = _katago_program(engine.get("katago", ""), katrain_package, which)
    model = _existing_file(engine.get("model", ""), "model", katrain_package)
    settings = _existing_file(engine.get("config", ""), "analysis settings", katrain_package)
    command = [str(katago), "analysis", "-model", str(model)]
    human_model = (engine.get("humanlike_model") or "").strip()
    if human_model:
        command += ["-human-model", str(_existing_file(human_model, "human-like model", katrain_package))]
    command += ["-config", str(settings), "-override-config", f"homeDataDir={os.path.expanduser(KATRAIN_DATA_FOLDER)}"]
    return EngineCommand(tuple(command), False, max_visits)


def _backend(engine: dict) -> str:
    """Return KaTrain's engine type: "local", "remote" or "custom" (KaTrain's resolve_engine_backend)."""
    backend = (engine.get("backend") or "").strip().lower()
    if backend in ("local", "remote", "custom"):
        return backend
    elif (engine.get("remote_url") or "").strip():
        return "remote"
    elif (engine.get("altcommand") or "").strip():
        return "custom"
    else:
        return "local"


# Places of the KataGo program that comes with KaTrain, inside the KaTrain program folder.
_BUNDLED_KATAGO = ("KataGo/katago-osx", "KataGo/katago", "KataGo/katago.exe")


def _katago_program(text: str, katrain_package: Path | None, which: Callable[[str], str | None]) -> Path:
    """Find the KataGo program, in the same way as KaTrain.

    An empty setting means the KataGo that comes with KaTrain. If it is not found
    (or the KaTrain folder is not given), "katago" is looked for in the PATH, as
    KaTrain does on a Mac (for example, KataGo installed with Homebrew).
    A setting without "/" is a program name, which is also looked for in the PATH.
    """
    text = text.strip()
    if not text:
        for bundled in _BUNDLED_KATAGO:
            if katrain_package is not None and (katrain_package / bundled).is_file():
                return katrain_package / bundled
        text = "katago"
    if "/" not in text and "\\" not in text:
        found = which(text)
        if found is None:
            raise KataGoNotFoundError(f"KataGo ({text}) is not found in the PATH")
        return Path(found)
    return _existing_file(text, "KataGo", katrain_package)


def _existing_file(text: str, name: str, katrain_package: Path | None) -> Path:
    """Resolve a path from the settings, and check that the file exists."""
    if not text.strip():
        raise KataGoNotFoundError(f"the {name} is not set")
    path = resolve_path(text, katrain_package)
    if not path.is_file():
        raise KataGoNotFoundError(f"the {name} is not found: {path}")
    return path


def katrain_package(folder: str, candidates: Iterable[Path] | None = None) -> Path | None:
    """Return the "katrain" folder of the KaTrain program, for paths that start with "katrain/".

    Args:
        folder: The folder set on the settings screen. It may be the "katrain" folder itself,
            or a folder that has it inside. "" means: look in the usual places.
        candidates: The places to look in when folder is "" (see find_katrain_package).
            Tests pass their own.

    Returns:
        The folder, or None if it is not found.
    """
    if folder.strip():
        path = Path(folder.strip()).expanduser()
        for place in (path, path / "katrain", path / "_internal" / "katrain"):
            if _is_katrain_package(place):
                return place
        return None
    return find_katrain_package(candidates)


def find_katrain_package(candidates: Iterable[Path] | None = None) -> Path | None:
    """Look for the "katrain" folder of an installed KaTrain in the usual places.

    Args:
        candidates: The places to look in. None means katrain_places().

    Returns:
        The first place that looks like KaTrain's "katrain" folder, or None.
    """
    for place in katrain_places() if candidates is None else candidates:
        if _is_katrain_package(place):
            return place
    return None


def katrain_places() -> list[Path]:
    """Return the usual places of KaTrain's "katrain" folder on this computer.

    First a KaTrain installed with pip in the same Python, then the places where KaTrain's
    programs for Windows and macOS are usually put, then KaTrain installed with pipx.
    These are guesses: the folder can always be set on the settings screen.
    """
    places = []
    spec = importlib.util.find_spec("katrain")
    if spec is not None and spec.origin:
        places.append(Path(spec.origin).parent)
    home = Path.home()
    if sys.platform == "win32":
        roots = [Path(os.environ["LOCALAPPDATA"]) / "Programs"] if os.environ.get("LOCALAPPDATA") else []
        roots += [Path(os.environ[name]) for name in ("PROGRAMFILES", "PROGRAMFILES(X86)") if os.environ.get(name)]
        roots += [home / "Desktop", home / "Downloads", home]
        for root in roots:
            places += [root / "KaTrain" / "katrain", root / "KaTrain" / "_internal" / "katrain"]
        places += sorted((home / "pipx" / "venvs" / "katrain").glob("Lib/site-packages/katrain"))
    elif sys.platform == "darwin":
        app = Path("/Applications/KaTrain.app/Contents")
        places += [app / "Resources" / "katrain", app / "Frameworks" / "katrain", app / "MacOS" / "katrain"]
    places += sorted((home / ".local" / "pipx" / "venvs" / "katrain").glob("lib/python3*/site-packages/katrain"))
    places += sorted((home / ".local" / "lib").glob("python3*/site-packages/katrain"))
    return places


def _is_katrain_package(path: Path) -> bool:
    """Return True if a folder looks like the "katrain" folder of the KaTrain program."""
    return path.is_dir() and any((path / mark).is_dir() for mark in KATRAIN_PACKAGE_MARKS)
