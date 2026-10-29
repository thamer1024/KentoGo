"""What an AI provider must do for the AI commentary (the providers themselves are in commentary.providers).

A provider sends a prompt to an AI and returns its answer. While the answer is made, the
provider gives the text to on_text as it arrives, so that a screen can show it, and it
stops early when cancel is set.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from kentogo.commentary.prompt import Prompt


@dataclass(frozen=True)
class Generation:
    """The AI's answer and its size.

    Attributes:
        text: The whole answer.
        input_tokens: The tokens of the prompt (0 if not known).
        output_tokens: The tokens of the answer (0 if not known).
        truncated: True if the answer was cut at the largest length.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    truncated: bool = False


# Why the AI could not be asked (the screen chooses the words).
ERROR_NO_PACKAGE = "no_package"  # The Python package of the API is not installed.
ERROR_NO_KEY = "no_key"  # The environment variable with the API key is not set.
ERROR_AUTHENTICATION = "authentication"  # The API key is wrong.
ERROR_CREDIT = "credit"  # No credit (balance) left.
ERROR_PERMISSION = "permission"  # The key may not use the model.
ERROR_NOT_FOUND = "not_found"  # The model (or the address) does not exist.
ERROR_RATE_LIMIT = "rate_limit"  # Too many requests, or the monthly limit was reached.
ERROR_OVERLOADED = "overloaded"  # The AI is busy or has a problem; try again later.
ERROR_CONNECTION = "connection"  # No connection to the AI, or no reply in time.
ERROR_OTHER = "other"


class ProviderError(Exception):
    """The AI could not be asked.

    Attributes:
        kind: Why, one of the ERROR_ constants.
        detail: The message of the API, or more information ("" if none).
    """

    def __init__(self, kind: str, detail: str = ""):
        """Make the error with its kind and detail."""
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class Provider(Protocol):
    """Sends a prompt to an AI."""

    def generate(self, prompt: Prompt, on_text: Callable[[str], None], cancel: threading.Event) -> Generation:
        """Ask the AI.

        Args:
            prompt: The prompt.
            on_text: Called with each piece of the answer as it arrives.
            cancel: When set, the provider stops as soon as it can (the answer is then not used).

        Returns:
            The answer.

        Raises:
            ProviderError: If the AI could not be asked.
        """
        ...
