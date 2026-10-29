"""The items of the settings screen, and how their texts become settings.

The settings screen shows one input for each FieldSpec in FIELDS. This module
turns the settings into the values of the inputs, and the values back into
settings, without Kivy, so that it can be tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from kentogo.app_settings import AppSettings
from kentogo.commentary.commentary_settings import PROVIDERS
from kentogo.katago.engine_settings import JUDGE_MODELS, EngineSettings
from kentogo.katago.locate import KataGoNotFoundError, read_engine_config, resolve_path
from kentogo.quiz.quiz_settings import ORDERS, QuizSettings
from kentogo.repetition.modes import PRIORITIES, REVIEW_MODES
from kentogo.seichi.seichi_settings import ORDERS as SEICHI_ORDERS

# Kinds of inputs.
KIND_FILE = "file"  # A path of a file. The screen says when the file does not exist.
KIND_FOLDER = "folder"  # A path of a folder.
KIND_TEXT = "text"
KIND_INT = "int"
KIND_FLOAT = "float"
KIND_BOOL = "bool"  # A check box.
KIND_CHOICE = "choice"  # A list to choose from.

# Groups of inputs, shown as separate boxes on the screen.
GROUP_KATAGO = "katago"
GROUP_GENERAL = "general"
GROUP_QUIZ = "quiz"
GROUP_ENGINE = "engine"
GROUP_JUDGE = "judge"
GROUP_REVIEW = "review"
GROUP_SEICHI = "seichi"
GROUP_COMMENTARY = "commentary"


@dataclass(frozen=True)
class FieldSpec:
    """One input of the settings screen.

    Attributes:
        key: The key of the value in its part of settings.json.
        section: The part of settings.json: "quiz", "engine", "seichi" or "commentary".
        kind: The kind of input, such as KIND_INT.
        group: The box on the screen where the input is shown.
        choices: The values to choose from, for KIND_CHOICE.
        name: The name of the input on the form, when the key is used by another part too
            (the AI's "model" and KataGo's "model"). "" means the key.
    """

    key: str
    section: str
    kind: str
    group: str
    choices: tuple[str, ...] = ()
    name: str = ""

    @property
    def id(self) -> str:
        """Return the name of the input on the form: the keys of form values, inputs and texts."""
        return self.name or self.key


FIELDS = (
    FieldSpec("katrain_config", "engine", KIND_FILE, GROUP_KATAGO),
    FieldSpec("katrain_folder", "engine", KIND_FOLDER, GROUP_KATAGO),
    FieldSpec("katago", "engine", KIND_FILE, GROUP_KATAGO),
    FieldSpec("model", "engine", KIND_FILE, GROUP_KATAGO),
    FieldSpec("humanlike_model", "engine", KIND_FILE, GROUP_KATAGO),
    FieldSpec("config", "engine", KIND_FILE, GROUP_KATAGO),
    FieldSpec("compare_model", "engine", KIND_FILE, GROUP_KATAGO),
    FieldSpec("games_folder", "quiz", KIND_FOLDER, GROUP_GENERAL),
    FieldSpec("my_names", "quiz", KIND_TEXT, GROUP_GENERAL),
    FieldSpec("use_seichi", "seichi", KIND_BOOL, GROUP_GENERAL),
    FieldSpec("session_limit", "quiz", KIND_INT, GROUP_QUIZ),
    FieldSpec("problems_per_game", "quiz", KIND_INT, GROUP_QUIZ),
    FieldSpec("min_points_lost", "quiz", KIND_FLOAT, GROUP_QUIZ),
    FieldSpec("skip_opening_moves", "quiz", KIND_INT, GROUP_QUIZ),
    FieldSpec("include_undone_moves", "quiz", KIND_BOOL, GROUP_QUIZ),
    FieldSpec("decided_winrate", "quiz", KIND_FLOAT, GROUP_QUIZ),
    FieldSpec("decided_lead", "quiz", KIND_FLOAT, GROUP_QUIZ),
    FieldSpec("order", "quiz", KIND_CHOICE, GROUP_QUIZ, ORDERS),
    FieldSpec("rotate", "quiz", KIND_BOOL, GROUP_QUIZ),
    FieldSpec("swap_colors", "quiz", KIND_BOOL, GROUP_QUIZ),
    FieldSpec("use_katago", "engine", KIND_BOOL, GROUP_ENGINE),
    FieldSpec("max_visits", "engine", KIND_INT, GROUP_ENGINE),
    FieldSpec("wide_root_noise", "engine", KIND_FLOAT, GROUP_ENGINE),
    FieldSpec("use_compare", "engine", KIND_BOOL, GROUP_ENGINE),
    FieldSpec("compare_max_visits", "engine", KIND_INT, GROUP_ENGINE),
    FieldSpec("estimate_visits", "engine", KIND_INT, GROUP_ENGINE),
    FieldSpec("judge_model", "engine", KIND_CHOICE, GROUP_ENGINE, JUDGE_MODELS),
    FieldSpec("small_problem_threshold", "quiz", KIND_FLOAT, GROUP_JUDGE),
    FieldSpec("pass_ratio", "quiz", KIND_FLOAT, GROUP_JUDGE),
    FieldSpec("tolerance", "quiz", KIND_FLOAT, GROUP_JUDGE),
    FieldSpec("review_mode", "quiz", KIND_CHOICE, GROUP_REVIEW, REVIEW_MODES),
    FieldSpec("review_streak", "quiz", KIND_INT, GROUP_REVIEW),
    FieldSpec("priority", "quiz", KIND_CHOICE, GROUP_REVIEW, PRIORITIES),
    FieldSpec("seichi_session_limit", "seichi", KIND_INT, GROUP_SEICHI),
    FieldSpec("seichi_order", "seichi", KIND_CHOICE, GROUP_SEICHI, SEICHI_ORDERS),
    FieldSpec("seichi_priority", "seichi", KIND_CHOICE, GROUP_SEICHI, PRIORITIES),
    FieldSpec("seichi_review_mode", "seichi", KIND_CHOICE, GROUP_SEICHI, REVIEW_MODES),
    FieldSpec("seichi_review_streak", "seichi", KIND_INT, GROUP_SEICHI),
    FieldSpec("provider", "commentary", KIND_CHOICE, GROUP_COMMENTARY, PROVIDERS, name="ai_provider"),
    FieldSpec("model", "commentary", KIND_TEXT, GROUP_COMMENTARY, name="ai_model"),
    FieldSpec("base_url", "commentary", KIND_TEXT, GROUP_COMMENTARY, name="ai_base_url"),
    FieldSpec("api_key_env", "commentary", KIND_TEXT, GROUP_COMMENTARY, name="ai_api_key_env"),
    FieldSpec("max_tokens", "commentary", KIND_INT, GROUP_COMMENTARY, name="ai_max_tokens"),
)


# The settings are shown on several screens, opened from the menu, in the same way
# as KaTrain splits them ("General & Engine settings", "Teaching/Analysis settings", ...).
PAGE_GENERAL = "general"  # KataGo's files, the games folder and names, and the engine.
PAGE_PRESETS = "presets"  # The recommended numbers of visits for each kind of computer (katago.presets).
PAGE_QUIZ = "quiz"  # Choosing and asking problems, and judging answers.
PAGE_REVIEW = "review"  # Reviews, and the order of new problems and reviews.
PAGE_SEICHI = "seichi"  # The territory counting practice: the order of the games, counting again, the limit.
PAGE_COMMENTARY = "commentary"  # The AI commentary: which AI and model, and the API key's variable.
PAGES = (PAGE_GENERAL, PAGE_PRESETS, PAGE_QUIZ, PAGE_REVIEW, PAGE_SEICHI, PAGE_COMMENTARY)
PAGE_GROUPS = {
    PAGE_GENERAL: (GROUP_KATAGO, GROUP_GENERAL, GROUP_ENGINE),
    PAGE_PRESETS: (),  # Only buttons (see gui.settings_popup).
    PAGE_QUIZ: (GROUP_QUIZ, GROUP_JUDGE),
    PAGE_REVIEW: (GROUP_REVIEW,),
    PAGE_SEICHI: (GROUP_SEICHI,),
    PAGE_COMMENTARY: (GROUP_COMMENTARY,),
}


# The engine inputs that come from KaTrain's local engine settings ("KaTrainから読み込む").
KATRAIN_ENGINE_KEYS = (
    "katrain_config",
    "katago",
    "model",
    "humanlike_model",
    "config",
    "max_visits",
    "wide_root_noise",
)


class FormError(ValueError):
    """Raised when some inputs are wrong.

    Attributes:
        errors: A dict from the key of each wrong input to a message.
    """

    def __init__(self, errors: dict[str, str]):
        """Keep the messages of the wrong inputs."""
        super().__init__("; ".join(f"{key}: {message}" for key, message in errors.items()))
        self.errors = errors


def form_values(settings: AppSettings) -> dict[str, str | bool]:
    """Return the values to show in the inputs: a text for each input, or True/False for a check box.

    Args:
        settings: All settings.
    """
    sections = settings.sections()
    values: dict[str, str | bool] = {}
    for spec in FIELDS:
        value = sections[spec.section][spec.key]
        if spec.key == "my_names":
            values[spec.id] = ", ".join(value)
        elif spec.kind == KIND_BOOL:
            values[spec.id] = bool(value)
        else:
            values[spec.id] = str(value)
    return values


def settings_from_form(values: dict[str, str | bool], settings: AppSettings) -> AppSettings:
    """Make new settings from the values of the inputs.

    Args:
        values: The values of the inputs (see form_values).
        settings: The current settings. Keys that are not in the form keep their values.

    Returns:
        The new settings.

    Raises:
        FormError: If some inputs are wrong. Its errors tell which ones.
    """
    sections = settings.sections()
    errors: dict[str, str] = {}
    for spec in FIELDS:
        try:
            sections[spec.section][spec.key] = _parse(spec, values[spec.id])
        except ValueError as error:
            errors[spec.id] = str(error)
    if errors:
        raise FormError(errors)
    try:
        return AppSettings.from_sections(sections)
    except ValueError as error:
        raise FormError({"": str(error)}) from error


def values_from_katrain(settings: AppSettings) -> dict[str, str | bool]:
    """Return the values of the engine inputs, copied from KaTrain's config.json.

    The paths, the number of visits and the noise are copied (KATRAIN_ENGINE_KEYS).
    The other engine inputs are not in KaTrain, so they keep their values.

    Args:
        settings: All settings. engine.katrain_config tells where KaTrain's config.json is.

    Returns:
        A dict from the key of each engine input to its new value.

    Raises:
        KataGoNotFoundError: If KaTrain's config.json cannot be read.
        ValueError: If its engine settings are wrong.
    """
    path = settings.engine.katrain_config
    katrain = EngineSettings.from_katrain(read_engine_config(path), path)
    values = form_values(replace(settings, engine=katrain))
    return {key: values[key] for key in KATRAIN_ENGINE_KEYS}


def needs_rereading(old: QuizSettings, new: QuizSettings) -> bool:
    """Return True if new settings make the next start read all SGF files again (which can take long).

    The problem cache keeps problems made with the old conditions for choosing
    problems, and only for the old games folder. Changing either of them makes
    the next start read every file.
    """
    return old.extract != new.extract or old.games_folder.strip() != new.games_folder.strip()


def count_games(folder: str) -> int:
    """Return the number of SGF files in a games folder (0 if it is not a folder)."""
    path = Path(folder.strip()).expanduser()
    return len(list(path.glob("*.sgf"))) if folder.strip() and path.is_dir() else 0


def path_exists(text: str, kind: str, katrain_folder: Path | None = None) -> bool:
    """Return True if a path input names an existing file or folder (or is empty, which is allowed).

    Args:
        text: The path in the input.
        kind: KIND_FILE or KIND_FOLDER.
        katrain_folder: The "katrain" folder of the KaTrain program, for paths that start with
            "katrain/" (see katago.locate.katrain_package). Without it, such paths do not exist.
    """
    if not text.strip():
        return True
    try:
        path = resolve_path(text, katrain_folder)
    except KataGoNotFoundError:
        return False
    return path.is_dir() if kind == KIND_FOLDER else path.is_file()


def _parse(spec: FieldSpec, value: str | bool):
    """Turn the value of one input into the value for settings.json.

    Raises:
        ValueError: If the value cannot be used. The message says what is expected.
    """
    if spec.kind == KIND_BOOL:
        return bool(value)
    text = str(value).strip()
    if spec.key == "my_names":
        return [name.strip() for name in re.split(r"[,、，]", text) if name.strip()]
    elif spec.kind == KIND_INT:
        if not re.fullmatch(r"\d+", text):
            raise ValueError("a whole number is needed")
        return int(text)
    elif spec.kind == KIND_FLOAT:
        try:
            return float(text)
        except ValueError as error:
            raise ValueError("a number is needed") from error
    elif spec.kind == KIND_CHOICE and text not in spec.choices:
        raise ValueError(f"one of {spec.choices} is needed")
    return text
