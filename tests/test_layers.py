"""Tests of the structure: which parts of KentoGo may use which (read from the imports of the source).

The parts are kept apart so that each can be changed (and reviewed) on its own:

- The shared layers (common, record, mistakes, katago, repetition) are used by the practices.
  They never use a practice or a screen.
- The practices (quiz, review, seichi, commentary, viewer, analysis) never use each other or a screen.
  The modules at the top of the package (app, today, answers, engines, ...) connect them.
- Only the screens (gui) and the app use Kivy, and no screen uses the app.
- Only the app's screen (gui.kentogo_app) opens the other screens.
- The screens do not use the histories: they are given what reads and keeps the results.
"""

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "src" / "kentogo"

# What each part may use, besides itself (the modules at the top of the package are named "kentogo.<module>").
ALLOWED = {
    "common": {"vendor"},
    "vendor": set(),
    "record": {"common", "vendor"},
    "mistakes": {"common", "record"},
    "katago": {"common", "vendor"},
    "repetition": set(),
    "quiz": {"common", "record", "mistakes", "katago"},
    "review": {"repetition"},
    "seichi": {"common", "repetition", "vendor"},
    "commentary": {"common", "record", "mistakes"},
    "viewer": {"common", "record", "mistakes", "katago"},
    "analysis": {"common", "record", "katago", "vendor"},
}
LOGIC = set(ALLOWED)
HISTORIES = {"kentogo.commentary.history", "kentogo.review.history", "kentogo.seichi.seichi_history"}


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


def test_the_screens_do_not_use_the_histories():
    """What is read from and kept in a history is decided outside the screens (see answers and seichi_plan)."""
    for path in files_of("gui"):
        assert imports_of(path) & HISTORIES == set(), path.name


def test_the_screens_do_not_open_a_history():
    """The screens of the AI commentary call the workspace, which opens the history for each piece of work."""
    for path in files_of("gui"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "open_history" not in names, path.name


@pytest.mark.parametrize(
    ("file_name", "unwanted"),
    [
        ("engines.py", "kentogo.quiz"),
        ("today.py", "kentogo.commentary."),
        ("fights_today.py", "kentogo.commentary."),
        ("fights_today.py", "kentogo.report"),
        ("fights_today.py", "kentogo.today"),
        ("report.py", "kentogo.commentary."),
        ("quiz_trial.py", "kentogo.commentary."),
    ],
)
def test_the_modules_at_the_top_stay_apart(file_name, unwanted):
    """KataGo does not know the quiz, the local fights do not know the report or the quiz's today."""
    assert [module for module in imports_of(SOURCE / file_name) if module.startswith(unwanted)] == []


def test_only_the_connecting_module_reads_the_commentary_history_for_the_practices():
    """The color and the rank given for the AI commentary come through commentary_inputs."""
    readers = {path.name for path in SOURCE.glob("*.py") if "kentogo.commentary.history" in imports_of(path)}
    assert readers <= {"commentary_inputs.py", "commentary_cli.py"}


def test_the_screens_do_not_read_sgf_files():
    """The screens get what is in a game from record (see record.game_record)."""
    for path in files_of("gui"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "kentogo.common":
                assert "sgf" not in {alias.name for alias in node.names}, path.name
        assert "kentogo.common.sgf" not in imports_of(path), path.name


def test_the_basic_texts_do_not_know_the_practices():
    """The texts of each practice are put together in its own module; gui.texts only finds the words."""
    used = {module for module in imports_of(SOURCE / "gui" / "texts.py") if module.startswith("kentogo.")}
    assert used == {"kentogo.gui.source_texts", "kentogo.notice"}


def test_every_part_is_named():
    """A new package must be put into ALLOWED (or be the screens), so that it is checked too."""
    packages = {path.name for path in SOURCE.iterdir() if path.is_dir() and (path / "__init__.py").exists()}
    assert packages - {"gui"} == LOGIC
