"""The AI providers: Claude's API, and the OpenAI-compatible API (ChatGPT, Gemini, DeepSeek, Ollama and others).

The Python packages of the APIs (anthropic, openai) are optional: they are installed with
`uv sync --extra ai` (or `pip install kentogo[ai]`). Without them, make_provider raises
ProviderError(ERROR_NO_PACKAGE), and the paste mode still works.

The API key is read from the environment variable named in the settings, and never kept.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from kentogo.commentary.commentary_settings import PROVIDER_ANTHROPIC, CommentarySettings
from kentogo.commentary.prompt import Prompt
from kentogo.commentary.provider_base import (
    ERROR_AUTHENTICATION,
    ERROR_CONNECTION,
    ERROR_CREDIT,
    ERROR_NO_KEY,
    ERROR_NO_PACKAGE,
    ERROR_NOT_FOUND,
    ERROR_OTHER,
    ERROR_OVERLOADED,
    ERROR_PERMISSION,
    ERROR_RATE_LIMIT,
    Generation,
    Provider,
    ProviderError,
)

# Makes the client of an API from (api_key, base_url). Tests give a fake one.
ClientFactory = Callable[[str, str | None], Any]


def make_provider(
    settings: CommentarySettings, environ: Mapping[str, str] = os.environ, client_factory: ClientFactory | None = None
) -> Provider:
    """Make the provider chosen in the settings.

    Args:
        settings: The settings of the AI commentary.
        environ: The environment variables (tests give their own).
        client_factory: Makes the client of the API (None: the real package).

    Returns:
        The provider.

    Raises:
        ProviderError: If the API key is not set, or the package of the API is not installed.
    """
    api_key = environ.get(settings.api_key_env, "").strip()
    if not api_key:
        raise ProviderError(ERROR_NO_KEY, settings.api_key_env)
    if settings.provider == PROVIDER_ANTHROPIC:
        factory = client_factory or _anthropic_client
        return AnthropicProvider(settings, factory(api_key, settings.base_url or None))
    factory = client_factory or _openai_client
    return OpenAICompatibleProvider(settings, factory(api_key, settings.base_url or None))


class AnthropicProvider:
    """Claude, through Anthropic's API (the anthropic package)."""

    def __init__(self, settings: CommentarySettings, client: Any):
        """Keep the settings and the client (anthropic.Anthropic or a fake one)."""
        self.settings = settings
        self.client = client

    def generate(self, prompt: Prompt, on_text: Callable[[str], None], cancel: threading.Event) -> Generation:
        """Ask Claude, giving the answer to on_text as it arrives (see provider_base.Provider)."""
        parts: list[str] = []
        try:
            with self.client.messages.stream(**self._request(prompt)) as stream:
                if _take_texts(stream.text_stream, parts, on_text, cancel):
                    return Generation("".join(parts))  # Cancelled: what has arrived so far.
                message = stream.get_final_message()
        except Exception as error:
            raise _provider_error(error) from error
        usage = message.usage
        tokens_in, tokens_out = usage.input_tokens or 0, usage.output_tokens or 0
        truncated = message.stop_reason == "max_tokens"
        return Generation("".join(parts), tokens_in, tokens_out, truncated)

    def _request(self, prompt: Prompt) -> dict:
        """Return the arguments of the request."""
        return {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "system": prompt.system,
            "messages": [{"role": "user", "content": prompt.user}],
        }


class OpenAICompatibleProvider:
    """An AI with an OpenAI-compatible API (the openai package): ChatGPT, Gemini, DeepSeek, Ollama and others."""

    def __init__(self, settings: CommentarySettings, client: Any):
        """Keep the settings and the client (openai.OpenAI or a fake one)."""
        self.settings = settings
        self.client = client

    def generate(self, prompt: Prompt, on_text: Callable[[str], None], cancel: threading.Event) -> Generation:
        """Ask the AI, giving the answer to on_text as it arrives (see provider_base.Provider)."""
        parts: list[str] = []
        usage, finish = None, None
        try:
            for chunk in self.client.chat.completions.create(**self._request(prompt)):
                usage = getattr(chunk, "usage", None) or usage
                finish = _take_chunk(chunk, parts, on_text) or finish
                if cancel.is_set():
                    return Generation("".join(parts))  # Cancelled: what has arrived so far.
        except Exception as error:
            raise _provider_error(error) from error
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        return Generation("".join(parts), tokens_in, tokens_out, finish == "length")

    def _request(self, prompt: Prompt) -> dict:
        """Return the arguments of the request.

        OpenAI's own API wants max_completion_tokens (newer models refuse max_tokens), while
        most other compatible APIs know only max_tokens.
        """
        limit_name = "max_tokens" if self.settings.base_url else "max_completion_tokens"
        return {
            "model": self.settings.model,
            "messages": [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user}],
            "stream": True,
            "stream_options": {"include_usage": True},
            limit_name: self.settings.max_tokens,
        }


def _anthropic_client(api_key: str, base_url: str | None) -> Any:
    """Make the client of Anthropic's API."""
    try:
        import anthropic
    except ImportError as error:
        raise ProviderError(ERROR_NO_PACKAGE, "anthropic") from error
    return anthropic.Anthropic(api_key=api_key, base_url=base_url)


def _openai_client(api_key: str, base_url: str | None) -> Any:
    """Make the client of an OpenAI-compatible API."""
    try:
        import openai
    except ImportError as error:
        raise ProviderError(ERROR_NO_PACKAGE, "openai") from error
    return openai.OpenAI(api_key=api_key, base_url=base_url)


def _take_texts(
    texts: Iterable[str], parts: list[str], on_text: Callable[[str], None], cancel: threading.Event
) -> bool:
    """Keep the pieces of the answer as they arrive, and give each to on_text. Returns True if it was cancelled."""
    for text in texts:
        parts.append(text)
        on_text(text)
        if cancel.is_set():
            return True
    return False


def _take_chunk(chunk: Any, parts: list[str], on_text: Callable[[str], None]) -> str | None:
    """Keep the text of one piece of an OpenAI-compatible answer, and give it to on_text.

    Returns:
        Why the answer ended (such as "length"), if this piece tells it, else None.
    """
    finish = None
    for choice in getattr(chunk, "choices", None) or []:
        finish = choice.finish_reason or finish
        text = getattr(choice.delta, "content", None) or ""
        if text:
            parts.append(text)
            on_text(text)
    return finish


def _provider_error(error: Exception) -> ProviderError:
    """Turn an error of an API package into a ProviderError, with its kind (as the user's script explains them)."""
    if isinstance(error, ProviderError):
        return error
    status = getattr(error, "status_code", None)
    detail = str(getattr(error, "message", "") or error)
    text = detail.lower()
    name = type(error).__name__
    if "credit balance" in text or "billing" in text or "quota" in text or status == 402:
        kind = ERROR_CREDIT
    elif status == 401 or "api key" in text or "authentication" in text:
        kind = ERROR_AUTHENTICATION
    elif status == 403:
        kind = ERROR_PERMISSION
    elif status == 404:
        kind = ERROR_NOT_FOUND
    elif status == 429:
        kind = ERROR_RATE_LIMIT
    elif status in (500, 502, 503, 529) or "overloaded" in text:
        kind = ERROR_OVERLOADED
    elif "Connection" in name or "Timeout" in name:
        kind = ERROR_CONNECTION
    else:
        kind = ERROR_OTHER
    return ProviderError(kind, detail)
