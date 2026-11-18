"""Find the folder of the user's games."""

from __future__ import annotations

from pathlib import Path

from kentogo.notice import Notice

# The folder of the project when KentoGo runs from its source (for example, downloaded from GitHub).
PROJECT_FOLDER = Path(__file__).resolve().parents[2]
# The games folder when KentoGo is installed as a program (not from its source).
INSTALLED_GAMES_FOLDER = Path("~/.kentogo/games")


def default_games_folder() -> Path:
    """Return the games folder used when the settings name none.

    From the source, it is the "games" folder of the project (empty at first, and kept out of
    git with the SGF files). An installed KentoGo uses "games" next to its settings instead.
    """
    if (PROJECT_FOLDER / "pyproject.toml").is_file():
        return PROJECT_FOLDER / "games"
    return INSTALLED_GAMES_FOLDER.expanduser()


def find_games_folder(
    argument: Path | None, setting: str, default: Path | None = None
) -> tuple[Path | None, Notice | None]:
    """Find the games folder: the one on the command line, or else the one in the settings, or else the default.

    The default folder is made if it does not exist yet. The app starts even without a
    usable folder, so that the user can set it on the settings screen.

    Args:
        argument: The folder given on the command line, or None.
        setting: The games_folder of the quiz settings ("" means the default folder).
        default: The default folder. None means default_games_folder() (tests give their own).

    Returns:
        A tuple (folder, problem). folder is None if there is no usable folder, and
        problem then tells why (None when there is a folder).
    """
    if argument is None and not setting.strip():
        folder = default or default_games_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None, Notice("folder_missing", {"folder": folder})
        return folder, None
    folder = argument or Path(setting.strip()).expanduser()
    if not folder.is_dir():
        return None, Notice("folder_missing", {"folder": folder})
    return folder, None
