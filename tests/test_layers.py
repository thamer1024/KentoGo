"""Tests of the structure: which parts of KentoGo may use which (read from the imports of the source).

The parts are kept apart so that each can be changed (and reviewed) on its own:

- The shared layers (common, record, mistakes, katago, repetition) are used by the practices.
  They never use a practice or a screen.
- The practices (quiz, review, seichi, commentary, viewer) never use each other or a screen.
  The modules at the top of the package (app, today, answers, engines, ...) connect them.
- Only the screens (gui) and the app use Kivy, and no screen uses the app.
- Only the app's screen (gui.kentogo_app) opens the other screens.
"""

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "src" / "kentogo"

# What each part may use, besides itself (the modules at the top of the package are named "kentogo.<module>").
ALLOWED = {
    "common": {"vendor"},
    "vendor": set(),
    "record": {"common"},
    "mistakes": {"common", "record"},
    "katago": {"common"},
    "repetition": set(),
    "quiz": {"common", "record", "mistakes", "katago"},
    "review": {"repetition"},
    "seichi": {"common", "repetition", "vendor"},
    "commentary": {"common", "record", "mistakes"},
    "viewer": {"common", "record", "mistakes", "katago"},
}
LOGIC = set(ALLOWED)


def imports_of(path: Path) -> set[str]:
    """Return the modules a file imports (also inside functions and TYPE_CHECKING)."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def part_of(module: str) -> str:
    """Return the part of a kentogo module: its package, or "kentogo.<module>" for a module at the top."""
    names = module.split(".")
    if len(names) == 2 and not (SOURCE / names[1]).is_dir():
        return module
    return names[1]


def files_of(part: str) -> list[Path]:
    """Return the source files of a package."""
    return sorted((SOURCE / part).rglob("*.py"))


@pytest.mark.parametrize("part", sorted(LOGIC))
def test_each_part_uses_only_what_it_may(part):
    """A shared layer or a practice uses only the parts below it, and never a screen or Kivy."""
    wrong = []
    for path in files_of(part):
        for module in imports_of(path):
            if module.startswith("kentogo.") and part_of(module) not in ALLOWED[part] | {part}:
                wrong.append(f"{path.name} -> {module}")
            if module.split(".")[0] == "kivy":
                wrong.append(f"{path.name} -> {module}")
    assert wrong == []


def test_the_screens_do_not_use_the_app():
    """The app makes the screens; a screen never goes back to it (see screen_setup and engines)."""
    for path in files_of("gui"):
        assert "kentogo.app" not in imports_of(path), path.name


def test_only_the_apps_screen_opens_the_other_screens():
    """A screen does not know the other screens: gui.kentogo_app moves between them."""
    for path in files_of("gui"):
        if path.name == "kentogo_app.py":
            continue
        screens = [module for module in imports_of(path) if module.endswith("_screen")]
        assert screens == [], path.name


def test_every_part_is_named():
    """A new package must be put into ALLOWED (or be the screens), so that it is checked too."""
    packages = {path.name for path in SOURCE.iterdir() if path.is_dir() and (path / "__init__.py").exists()}
    assert packages - {"gui"} == LOGIC
