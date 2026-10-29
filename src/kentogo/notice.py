"""A message for the user, given by the parts of KentoGo that do not use the screens.

Such a part does not choose the words: it gives the key of the text and the values to fill
in, and the screens turn it into words in the language of the screens (see gui.texts.notice_text).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Notice:
    """A message for the user.

    Attributes:
        key: The key of the text (see gui.texts).
        values: The values to fill into the text, such as {"reason": "..."}.
    """

    key: str
    values: dict = field(default_factory=dict)
