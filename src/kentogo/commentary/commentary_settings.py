"""Settings of the AI commentary, kept in the "commentary" part of settings.json.

They choose the AI and its model. The API key itself is never kept: only the name of the
environment variable that holds it (the user sets the variable outside KentoGo).

How many moves of a game are explained is not set here: it is the number of problems per
game of the quiz (see mistakes.extract.ExtractSettings.problems_per_game).

KentoGo does not show costs: prices change, and a price kept in the settings would become
wrong without the user noticing. Only the numbers of tokens are shown.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

PROVIDER_ANTHROPIC = "anthropic"  # Claude, through Anthropic's API.
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"  # ChatGPT, Gemini, DeepSeek, Ollama and others.
PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI_COMPATIBLE)


@dataclass(frozen=True)
class CommentarySettings:
    """The settings of the AI commentary.

    Attributes:
        provider: The kind of API, one of PROVIDERS.
        model: The name of the model, such as "claude-opus-5-5".
        base_url: The address of the API ("" for the provider's own address). For an
            OpenAI-compatible AI other than ChatGPT, this chooses the AI.
        api_key_env: The name of the environment variable that holds the API key.
        max_tokens: The largest length of an answer, in tokens.
    """

    provider: str = PROVIDER_ANTHROPIC
    model: str = "claude-opus-5-5"
    base_url: str = ""
    api_key_env: str = "ANTHROPIC_API_KEY"
    max_tokens: int = 15000

    @classmethod
    def from_dict(cls, values: dict) -> CommentarySettings:
        """Make the settings from the "commentary" part of settings.json.

        Args:
            values: The values. Missing keys get the default values, and unknown keys are ignored.

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        default = cls()
        kept = {}
        for item in fields(cls):
            value = values.get(item.name, getattr(default, item.name))
            kept[item.name] = _checked(item.name, value, type(getattr(default, item.name)))
        if kept["provider"] not in PROVIDERS:
            raise ValueError(f"wrong commentary setting: provider must be one of {PROVIDERS}: {kept['provider']!r}")
        if kept["max_tokens"] < 1:
            raise ValueError("wrong commentary setting: max_tokens must be 1 or more")
        return cls(**kept)

    def to_dict(self) -> dict:
        """Return the settings as a dict, for the "commentary" part of settings.json."""
        return {item.name: getattr(self, item.name) for item in fields(self)}


def _checked(name: str, value: object, kind: type) -> object:
    """Return the value if it has the right type, or raise ValueError."""
    if isinstance(value, kind) and not isinstance(value, bool):
        return value
    raise ValueError(f"wrong commentary setting: {name} must be {kind.__name__}: {value!r}")
