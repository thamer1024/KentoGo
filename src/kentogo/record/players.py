"""Find which color in a game is the user (the player who practices).

KaTrain writes the player names in one of two ways:

- A name that the user set for a human player, written as it is.
- A name made by KaTrain, such as "Human (Teaching Game)" or "AI (Human-like)".
  It is "type (subtype)" with a marker at the end, and the words are
  translated into the language that the user selected in KaTrain.

KaTrain writes the names again each time the game is saved, from the players set
at that time. So if the AI was changed to a human after the game, both names say
"Human". Two other things still tell which player was the AI:

- The rank (BR or WR): KaTrain writes it only for an AI, and does not remove it
  when the player is changed to a human.
- The file name: KaTrain makes it as "KaTrain_<black> vs <white> <date>.sgf"
  when the game is saved for the first time, and keeps it after that.

Games from other servers, such as Fox Weiqi, have the real names of both players.

Before all of these, the color that the user gave in the list of games for the AI
commentary is used (see commentary.history).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from kentogo.record.katrain_comment import INTERNAL_MARKER
from kentogo.record.katrain_texts import KATRAIN_TEXTS

HUMAN = "human"
AI = "ai"
UNKNOWN = "unknown"

# The file name that KaTrain gives a game (KaTrain 1.20.0, Game.generate_filename).
# The date is the time when the game was started.
KATRAIN_FILE_NAME = re.compile(r"KaTrain_(.+?) vs (.+) \d{4}-\d{2}-\d{2} \d{2} \d{2} \d{2}\.sgf", re.IGNORECASE)


def _texts_in_all_languages(*keys: str) -> set[str]:
    """Collect the texts of the given keys in all languages."""
    return {texts[key] for texts in KATRAIN_TEXTS.values() for key in keys}


def classify_katrain_name(name: str) -> str:
    """Tell whether a player name made by KaTrain (a PB or PW property) is a human or an AI.

    Args:
        name: The PB or PW property of a game.

    Returns:
        HUMAN or AI. UNKNOWN if the name was not made by KaTrain (it has no marker),
        or if it does not match any language.
    """
    if INTERNAL_MARKER not in name:
        return UNKNOWN
    return classify_player_text(name.replace(INTERNAL_MARKER, ""))


def classify_player_text(text: str) -> str:
    """Tell whether a "type (subtype)" text of KaTrain, without the marker, is a human or an AI.

    The subtype of a human is always "Normal Game" or "Teaching Game", so it
    is checked first. The subtype of an AI is the name of its playing style,
    and in some languages it can be the same word as "Human" (in French,
    an AI is "Artificiel (Humain)"). So the type is checked only after that.

    Args:
        text: The text, such as "Human (Teaching Game)" or a player name in a file name.

    Returns:
        HUMAN or AI, or UNKNOWN if the text does not match any language.
    """
    text = text.strip()
    match = re.fullmatch(r"(.*?)\s*\((.*)\)", text)
    player_type, subtype = (match[1].strip(), match[2].strip()) if match else (text, "")

    if subtype in _texts_in_all_languages("game:normal", "game:teach"):
        return HUMAN
    elif player_type in _texts_in_all_languages("player:human"):
        return HUMAN
    elif player_type in _texts_in_all_languages("player:ai"):
        return AI
    else:
        return UNKNOWN


def split_katrain_file_name(file_name: str) -> tuple[str, str] | None:
    """Return the black and white player names in a file name made by KaTrain.

    Args:
        file_name: The name of the SGF file (a folder part is ignored).

    Returns:
        (black, white), or None if the file name is not in KaTrain's form.
    """
    match = KATRAIN_FILE_NAME.fullmatch(Path(file_name).name)
    return (match[1], match[2]) if match else None


def detect_my_color(
    black_name: str,
    white_name: str,
    my_names: Iterable[str] = (),
    ranks: tuple[str, str] = ("", ""),
    file_name: str = "",
    recorded_color: str = "",
) -> str | None:
    """Find the color of the user in a game.

    The first of these that finds the color is used:

    0. The color that the user gave for this game (recorded_color).
    1. If exactly one player name is in my_names, that player is the user.
    2. If the names were made by KaTrain and one is a human and the other
       is an AI, the human is the user.
    3. If both names are KaTrain's "Human" and only one player has a rank,
       that player was the AI, and the other player is the user.
    4. If the file name was made by KaTrain, its player names are used as in 2.

    Args:
        black_name: The PB property of the game.
        white_name: The PW property of the game.
        my_names: The names that the user uses (for example, the user name on Fox Weiqi).
        ranks: The BR and WR properties of the game.
        file_name: The name of the SGF file.
        recorded_color: "B" or "W" if the user gave the color of this game, or "" otherwise.

    Returns:
        "B" or "W", or None if the color cannot be found
        (for example, a game between two humans).
    """
    return (
        _recorded(recorded_color)
        or _color_by_my_names(black_name, white_name, my_names)
        or _color_of_human(classify_katrain_name(black_name), classify_katrain_name(white_name))
        or _color_by_ranks(black_name, white_name, ranks)
        or _color_by_file_name(file_name)
    )


def _recorded(recorded_color: str) -> str | None:
    """Return the color that the user gave, if it is "B" or "W"."""
    return recorded_color if recorded_color in ("B", "W") else None


def _color_by_my_names(black_name: str, white_name: str, my_names: Iterable[str]) -> str | None:
    """Return the color whose name is in my_names, if exactly one is."""
    names = {name.strip() for name in my_names if name.strip()}
    black_is_mine = black_name.strip() in names
    white_is_mine = white_name.strip() in names
    if black_is_mine == white_is_mine:
        return None
    return "B" if black_is_mine else "W"


def _color_of_human(black_kind: str, white_kind: str) -> str | None:
    """Return the color of the human in a game between a human and an AI (kinds are HUMAN, AI or UNKNOWN)."""
    if (black_kind, white_kind) == (HUMAN, AI):
        return "B"
    elif (black_kind, white_kind) == (AI, HUMAN):
        return "W"
    else:
        return None


def _color_by_ranks(black_name: str, white_name: str, ranks: tuple[str, str]) -> str | None:
    """Return the color without a rank, when both names are KaTrain's "Human" and only one player has a rank."""
    if (classify_katrain_name(black_name), classify_katrain_name(white_name)) != (HUMAN, HUMAN):
        return None
    black_rank, white_rank = (rank.strip() for rank in ranks)
    if black_rank and not white_rank:
        return "W"
    elif white_rank and not black_rank:
        return "B"
    else:
        return None


def _color_by_file_name(file_name: str) -> str | None:
    """Return the color of the human in the player names of a file name made by KaTrain."""
    names = split_katrain_file_name(file_name)
    if names is None:
        return None
    return _color_of_human(classify_player_text(names[0]), classify_player_text(names[1]))
