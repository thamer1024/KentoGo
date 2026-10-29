"""Tests for kentogo.commentary.providers, with fake API clients (no network)."""

import threading
from types import SimpleNamespace as Obj

import pytest

from kentogo.commentary.commentary_settings import PROVIDER_OPENAI_COMPATIBLE, CommentarySettings
from kentogo.commentary.prompt import Prompt
from kentogo.commentary.provider_base import (
    ERROR_AUTHENTICATION,
    ERROR_CONNECTION,
    ERROR_CREDIT,
    ERROR_NO_KEY,
    ERROR_NOT_FOUND,
    ERROR_OVERLOADED,
    ERROR_RATE_LIMIT,
    ProviderError,
)
from kentogo.commentary.providers import make_provider

PROMPT = Prompt("ROLE", "MESSAGE")
KEY = {"ANTHROPIC_API_KEY": "secret", "OPENAI_API_KEY": "secret"}


class FakeStream:
    """The stream of anthropic's client.messages.stream()."""

    def __init__(self, texts, stop_reason="end_turn"):
        self.text_stream = iter(texts)
        self.message = Obj(usage=Obj(input_tokens=1_000_000, output_tokens=500_000), stop_reason=stop_reason)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeAnthropic:
    """A fake anthropic client that remembers the request."""

    def __init__(self, stream=None, error=None):
        self.requests = []

        def make_stream(**request):
            self.requests.append(request)
            if error:
                raise error
            return stream

        self.messages = Obj(stream=make_stream)


def chunk(text=None, finish=None, usage=None):
    """A chunk of openai's streamed chat completion."""
    choices = [Obj(delta=Obj(content=text), finish_reason=finish)] if text is not None or finish else []
    return Obj(choices=choices, usage=usage)


class FakeOpenAI:
    """A fake openai client that remembers the request."""

    def __init__(self, chunks):
        self.requests = []

        def create(**request):
            self.requests.append(request)
            return iter(chunks)

        self.chat = Obj(completions=Obj(create=create))


def test_anthropic_streams_and_counts():
    """Claude's answer is given piece by piece, with the numbers of tokens."""
    client = FakeAnthropic(FakeStream(["Hel", "lo"]))
    provider = make_provider(CommentarySettings(), KEY, lambda key, url: client)
    pieces = []
    result = provider.generate(PROMPT, pieces.append, threading.Event())
    assert (result.text, pieces, result.input_tokens, result.output_tokens) == (
        "Hello",
        ["Hel", "lo"],
        1_000_000,
        500_000,
    )
    assert not result.truncated
    request = client.requests[0]
    assert (request["model"], request["system"], request["max_tokens"]) == ("claude-opus-5-5", "ROLE", 15000)
    assert request["messages"] == [{"role": "user", "content": "MESSAGE"}]


def test_anthropic_cut_and_cancel():
    """An answer cut at the largest length is told; cancel stops reading the answer."""
    provider = make_provider(CommentarySettings(), KEY, lambda key, url: FakeAnthropic(FakeStream(["a"], "max_tokens")))
    assert provider.generate(PROMPT, lambda text: None, threading.Event()).truncated
    cancel = threading.Event()
    cancel.set()
    provider = make_provider(CommentarySettings(), KEY, lambda key, url: FakeAnthropic(FakeStream(["a", "b"])))
    assert provider.generate(PROMPT, lambda text: None, cancel).text == "a"


def test_openai_compatible():
    """An OpenAI-compatible answer is read from its chunks; another address uses max_tokens."""
    usage = Obj(prompt_tokens=10, completion_tokens=20)
    client = FakeOpenAI([chunk("{"), chunk("}", "length"), chunk(usage=usage)])
    settings = CommentarySettings(PROVIDER_OPENAI_COMPATIBLE, "local", "http://localhost:11434/v1", "OPENAI_API_KEY")
    seen = []
    provider = make_provider(settings, KEY, lambda key, url: seen.append((key, url)) or client)
    result = provider.generate(PROMPT, lambda text: None, threading.Event())
    assert (result.text, result.input_tokens, result.output_tokens, result.truncated) == ("{}", 10, 20, True)
    assert seen == [("secret", "http://localhost:11434/v1")]
    request = client.requests[0]
    assert request["max_tokens"] == 15000 and request["stream"] and request["messages"][0]["content"] == "ROLE"
    settings = CommentarySettings(PROVIDER_OPENAI_COMPATIBLE, "gpt", "", "OPENAI_API_KEY")
    client = FakeOpenAI([chunk("x")])
    make_provider(settings, KEY, lambda key, url: client).generate(PROMPT, lambda text: None, threading.Event())
    assert "max_completion_tokens" in client.requests[0]


def test_no_key():
    """Without the environment variable, the AI cannot be asked."""
    with pytest.raises(ProviderError) as caught:
        make_provider(CommentarySettings(), {}, lambda key, url: None)
    assert (caught.value.kind, caught.value.detail) == (ERROR_NO_KEY, "ANTHROPIC_API_KEY")


class StatusError(Exception):
    """An error of an API package with a status code."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status_code = status
        self.message = message


class APIConnectionError(Exception):
    """An error named like the packages' connection error."""


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (StatusError(400, "Your credit balance is too low"), ERROR_CREDIT),
        (StatusError(401, "invalid x-api-key"), ERROR_AUTHENTICATION),
        (StatusError(404, "model not found"), ERROR_NOT_FOUND),
        (StatusError(429, "rate limit"), ERROR_RATE_LIMIT),
        (StatusError(529, "Overloaded"), ERROR_OVERLOADED),
        (APIConnectionError("no network"), ERROR_CONNECTION),
    ],
)
def test_api_errors(error, kind):
    """The errors of the API are told by their kind."""
    provider = make_provider(CommentarySettings(), KEY, lambda key, url: FakeAnthropic(error=error))
    with pytest.raises(ProviderError) as caught:
        provider.generate(PROMPT, lambda text: None, threading.Event())
    assert caught.value.kind == kind
