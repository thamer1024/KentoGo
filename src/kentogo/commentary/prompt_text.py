"""The parts of the prompt that the user can change, kept in a text file.

The parts that do not depend on the game are kept in a text file, so that the user can
change them with a text editor:

- system: the role of the AI (the system prompt).
- intro: the first sentence of the message. "{color}" is replaced with the user's color (such as 黒 or Black).
- about_me: lines about the user (weak points, goals, and so on). The rank and the
  opponent are added by KentoGo for each game.
- rules: the rules that the AI must keep.

Each part starts with a line such as "[[rules]]", and goes to the next such line.
There is a file for each language of the prompt (see commentary.language): the Japanese
one and the English one. The user's file is USER_FILE_NAMES[language] in the folder of the
settings file. If there is no such file, the default of the language (DEFAULT_FILES, shipped
with KentoGo) is used. A part that is missing from the user's file is taken from the
default, and the user is told.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from kentogo.commentary.language import JAPANESE, PROMPT_ENGLISH, PROMPT_JAPANESE, CommentaryLanguage

SECTIONS = ("system", "intro", "about_me", "rules")
_FOLDER = Path(__file__).resolve().parent
DEFAULT_FILES = {PROMPT_JAPANESE: _FOLDER / "default_prompt.txt", PROMPT_ENGLISH: _FOLDER / "default_prompt_en.txt"}
USER_FILE_NAMES = {PROMPT_JAPANESE: "commentary_prompt_jp.txt", PROMPT_ENGLISH: "commentary_prompt_en.txt"}
COLOR_PLACEHOLDER = "{color}"

_SECTION_LINE = re.compile(r"\[\[(\w+)\]\]")


PROBLEM_UNREADABLE = "unreadable"  # The file cannot be read (detail has the reason).
PROBLEM_MISSING = "missing"  # A part is missing, so the default is used.
PROBLEM_UNKNOWN = "unknown"  # A part has an unknown name, so it is not used.


@dataclass(frozen=True)
class PromptFileProblem:
    """A problem in the user's prompt file, to tell the user (the screen chooses the words).

    Attributes:
        path: The file.
        kind: PROBLEM_UNREADABLE, PROBLEM_MISSING or PROBLEM_UNKNOWN.
        section: The name of the part ("" for PROBLEM_UNREADABLE).
        detail: The error, for PROBLEM_UNREADABLE ("" otherwise).
    """

    path: Path
    kind: str
    section: str = ""
    detail: str = ""


@dataclass(frozen=True)
class PromptText:
    """The parts of the prompt that the user can change (see the module docstring).

    Attributes:
        system, intro, about_me, rules: The parts.
        language: The language of the commentary that the parts are written for.
    """

    system: str
    intro: str
    about_me: str
    rules: str
    language: CommentaryLanguage = JAPANESE


def parse_sections(text: str) -> dict[str, str]:
    """Split the text of a prompt file into its parts.

    Args:
        text: The text of the file.

    Returns:
        The parts by name, with spaces and empty lines at both ends removed.
        Unknown part names are kept too (the caller decides what to do with them).
        Lines before the first part are ignored.
    """
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        match = _SECTION_LINE.fullmatch(line.strip())
        if match:
            current = sections.setdefault(match[1], [])
        elif current is not None:
            current.append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def default_prompt_text(language: CommentaryLanguage = JAPANESE) -> PromptText:
    """Return the default parts of the language of the prompt, shipped with KentoGo."""
    sections = parse_sections(DEFAULT_FILES[language.prompt].read_text(encoding="utf-8"))
    return PromptText(**{name: sections[name] for name in SECTIONS}, language=language)


def user_prompt_path(settings_path: Path, prompt_language: str = PROMPT_JAPANESE) -> Path:
    """Return the path of the user's prompt file of a language of the prompt: in the folder of the settings file."""
    return settings_path.expanduser().parent / USER_FILE_NAMES[prompt_language]


def load_prompt_text(
    settings_path: Path, language: CommentaryLanguage = JAPANESE
) -> tuple[PromptText, list[PromptFileProblem]]:
    """Read the user's prompt file of the language of the prompt, or the default if there is none.

    Args:
        settings_path: Path of the settings file (the prompt file is next to it).
        language: The language of the commentary (its prompt chooses the file).

    Returns:
        The parts, and the problems to tell the user. Missing parts are taken from the default, so the parts can always be used.
    """
    default = default_prompt_text(language)
    path = user_prompt_path(settings_path, language.prompt)
    if not path.exists():
        return default, []
    try:
        sections = parse_sections(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        return default, [PromptFileProblem(path, PROBLEM_UNREADABLE, detail=str(error))]
    problems = [PromptFileProblem(path, PROBLEM_MISSING, name) for name in SECTIONS if name not in sections]
    problems += [PromptFileProblem(path, PROBLEM_UNKNOWN, name) for name in sections if name not in SECTIONS]
    values = {name: sections.get(name, getattr(default, name)) for name in SECTIONS}
    return PromptText(**values, language=language), problems


def create_user_prompt_file(settings_path: Path, prompt_language: str = PROMPT_JAPANESE) -> Path:
    """Make the user's prompt file of a language from its default, if it does not exist yet, so that the user can change it.

    Returns:
        The path of the user's prompt file (it is not changed if it already exists).

    Raises:
        OSError: If the file cannot be written.
    """
    path = user_prompt_path(settings_path, prompt_language)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_FILES[prompt_language].read_text(encoding="utf-8"), encoding="utf-8")
    return path
