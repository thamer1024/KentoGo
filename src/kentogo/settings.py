"""Read and write the settings file (settings.json).

The file has one part (section) for each feature, such as "quiz" and "engine".
Each feature reads and writes only its own section, and turns the dict into its
own settings class (for example, mistakes.extract.ExtractSettings.from_dict).
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path


class SettingsStore:
    """The settings file, with default values for missing sections and keys.

    Attributes:
        path: Path of the settings file.
    """

    def __init__(self, path: str | Path, defaults: dict[str, dict]):
        """Make a store. The file is not read until load() is called.

        Args:
            path: Path of the settings file.
            defaults: The default values, as {section name: {key: value}}.
        """
        self.path = Path(path)
        self._defaults = copy.deepcopy(defaults)
        self._sections = copy.deepcopy(defaults)

    def load(self) -> None:
        """Read the file. If it does not exist, the default values are used.

        Keys in the file replace the default values. Keys that are only in the
        defaults are kept, so new settings get their default values.

        Raises:
            ValueError: If the file is not a JSON object of sections.
        """
        self._sections = copy.deepcopy(self._defaults)
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"{self.path} is not valid JSON: {error}") from error
        if not isinstance(data, dict) or not all(isinstance(value, dict) for value in data.values()):
            raise ValueError(f"{self.path} must be a JSON object of sections")
        for name, values in data.items():
            self._sections.setdefault(name, {}).update(values)

    def section(self, name: str) -> dict:
        """Return a copy of one section. Changing the copy does not change the store.

        Args:
            name: Name of the section, such as "quiz".

        Returns:
            The values of the section, or an empty dict if there is no such section.
        """
        return copy.deepcopy(self._sections.get(name, {}))

    def set_section(self, name: str, values: dict) -> None:
        """Replace the values of one section. Call save() to write them to the file.

        Args:
            name: Name of the section.
            values: The new values. They must be values that JSON can store.
        """
        self._sections[name] = copy.deepcopy(values)

    def save(self) -> None:
        """Write all sections to the file.

        The file is first written to a temporary file and then replaces the old
        file, so the old file is not broken if writing fails.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self._sections, ensure_ascii=False, indent=2) + "\n"
        handle, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(text)
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
