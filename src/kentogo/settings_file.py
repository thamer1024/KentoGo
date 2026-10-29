"""The settings file of KentoGo (~/.kentogo/settings.json): where it is, its defaults, reading and writing it.

All settings of the app are read and written together (see app_settings.AppSettings). The
first time, the file is made with the default values, and the engine settings are copied
from KaTrain's config.json. This module does not use the screens, so the command line
tools can read the same settings (see commentary_cli).
"""

from __future__ import annotations

from pathlib import Path

from kentogo.app_settings import AppSettings
from kentogo.katago.engine_settings import EngineSettings
from kentogo.katago.locate import DEFAULT_KATRAIN_CONFIG, KataGoNotFoundError, read_engine_config
from kentogo.settings import SettingsStore

# Where the settings are kept (the same style as KaTrain's ~/.katrain).
SETTINGS_PATH = Path("~/.kentogo/settings.json")


def default_settings(katrain_config: Path = DEFAULT_KATRAIN_CONFIG) -> dict[str, dict]:
    """Return the default values of all sections of the settings file.

    The engine settings are copied from KaTrain's config.json if it can be read.

    Args:
        katrain_config: Path of KaTrain's config.json.
    """
    try:
        engine = EngineSettings.from_katrain(read_engine_config(katrain_config), str(katrain_config))
    except (KataGoNotFoundError, ValueError):
        engine = EngineSettings()
    return AppSettings(engine=engine).sections()


def load_settings(path: Path, katrain_config: Path = DEFAULT_KATRAIN_CONFIG) -> AppSettings:
    """Read the settings file. If it does not exist, make it with the default values.

    Args:
        path: Path of the settings file. "~" means the home folder.
        katrain_config: Path of KaTrain's config.json, to copy the engine settings from
            when the settings file is made.

    Returns:
        All settings.

    Raises:
        ValueError: If the file is broken or has wrong values.
    """
    store = SettingsStore(path.expanduser(), default_settings(katrain_config))
    store.load()
    if not store.path.exists():
        store.save()
    return AppSettings.from_sections({name: store.section(name) for name in ("quiz", "engine", "seichi", "commentary")})


def save_settings(path: Path, settings: AppSettings) -> None:
    """Write all settings to the settings file.

    Other sections in the file are kept as they are.

    Args:
        path: Path of the settings file. "~" means the home folder.
        settings: All settings.

    Raises:
        ValueError: If the file exists but is broken.
        OSError: If the file cannot be written.
    """
    store = SettingsStore(path.expanduser(), {})
    store.load()
    for name, values in settings.sections().items():
        store.set_section(name, values)
    store.save()
