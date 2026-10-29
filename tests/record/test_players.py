"""Tests for kentogo.record.players."""

from pathlib import Path

import pytest

from kentogo.record.katrain_comment import INTERNAL_MARKER
from kentogo.record.katrain_texts import KATRAIN_TEXTS
from kentogo.record.players import (
    AI,
    HUMAN,
    UNKNOWN,
    classify_katrain_name,
    classify_player_text,
    detect_my_color,
    split_katrain_file_name,
)


def katrain_name(player_type: str, subtype: str) -> str:
    """Make a player name in the same way as KaTrain's Game.update_root_properties."""
    return f"{player_type} ({subtype}){INTERNAL_MARKER}"


@pytest.mark.parametrize("language", sorted(KATRAIN_TEXTS))
def test_classify_all_languages(language):
    """Human and AI names made with the texts of each language are told apart."""
    texts = KATRAIN_TEXTS[language]
    assert classify_katrain_name(katrain_name(texts["player:human"], texts["game:normal"])) == HUMAN
    assert classify_katrain_name(katrain_name(texts["player:human"], texts["game:teach"])) == HUMAN
    assert classify_katrain_name(katrain_name(texts["player:ai"], "Some style")) == AI


def test_classify_real_names():
    """Real names from KaTrain 1.20.0 are classified correctly."""
    assert classify_katrain_name(katrain_name("人間", "指導対局")) == HUMAN
    assert classify_katrain_name(katrain_name("AI", "人間流")) == AI
    assert classify_katrain_name(katrain_name("Human", "Teaching Game")) == HUMAN
    assert classify_katrain_name(katrain_name("AI", "Human-like")) == AI


def test_classify_french_ai_with_human_style():
    """A French AI with the "Humain" style is an AI, though its subtype is the same word as "Human"."""
    assert classify_katrain_name(katrain_name("Artificiel", "Humain")) == AI


def test_classify_names_not_made_by_katrain():
    """A name without the marker is not classified."""
    assert classify_katrain_name("Taro") == UNKNOWN
    assert classify_katrain_name("人間 (指導対局)") == UNKNOWN


def test_detect_human_against_ai():
    """In a game between a human and an AI, the human is the user."""
    human = katrain_name("人間", "指導対局")
    ai = katrain_name("AI", "人間流")
    assert detect_my_color(human, ai) == "B"
    assert detect_my_color(ai, human) == "W"


def test_detect_by_my_names():
    """A name in my_names decides the color, as in a game from Fox Weiqi."""
    assert detect_my_color("opponent", "Taro", my_names=["Taro"]) == "W"
    assert detect_my_color(" Taro ", "opponent", my_names=["Taro", ""]) == "B"


def test_detect_unknown():
    """The color is not found in games between two humans or between unknown players."""
    human = katrain_name("人間", "通常対局")
    assert detect_my_color(human, human) is None
    assert detect_my_color("player1", "player2") is None
    assert detect_my_color("Taro", "Taro", my_names=["Taro"]) is None


def test_classify_player_text_without_marker():
    """A "type (subtype)" text without the marker, as in a file name, is classified."""
    assert classify_player_text("人間 (通常対局)") == HUMAN
    assert classify_player_text("AI (人間流)") == AI
    assert classify_player_text("Artificiel (Humain)") == AI
    assert classify_player_text("Taro") == UNKNOWN


def test_split_katrain_file_name():
    """The player names are taken from a file name made by KaTrain, and other names give None."""
    name = "KaTrain_AI (人間流) vs 人間 (通常対局) 2026-10-12 05 07 05.sgf"
    assert split_katrain_file_name(name) == ("AI (人間流)", "人間 (通常対局)")
    assert split_katrain_file_name(str(Path("games") / name)) == ("AI (人間流)", "人間 (通常対局)")
    assert split_katrain_file_name("game.sgf") is None
    assert split_katrain_file_name("KaTrain_AI vs Human.sgf") is None


def test_detect_by_rank_when_both_are_human():
    """When the AI was changed to a human after the game, the player with a rank was the AI."""
    human = katrain_name("人間", "通常対局")
    assert detect_my_color(human, human, ranks=("20級", "")) == "W"
    assert detect_my_color(human, human, ranks=("", "3段")) == "B"


def test_rank_does_not_decide_when_unclear():
    """Ranks on both players or on none do not decide, and ranks are not used for real names."""
    human = katrain_name("人間", "通常対局")
    assert detect_my_color(human, human, ranks=("20級", "20級")) is None
    assert detect_my_color(human, human, ranks=("", "")) is None
    assert detect_my_color("player1", "player2", ranks=("5段", "")) is None


def test_detect_by_file_name():
    """The player names in a file name made by KaTrain find the color."""
    human = katrain_name("人間", "通常対局")
    file_name = "KaTrain_AI (人間流) vs 人間 (指導対局) 2026-10-12 05 07 05.sgf"
    assert detect_my_color(human, human, file_name=file_name) == "W"
    file_name = "KaTrain_Human (Normal Game) vs AI (Human-like) 2026-10-12 05 07 05.sgf"
    assert detect_my_color(human, human, file_name=file_name) == "B"


def test_file_name_does_not_decide_when_unclear():
    """A file name with two humans, or not made by KaTrain, does not decide."""
    human = katrain_name("人間", "通常対局")
    assert (
        detect_my_color(human, human, file_name="KaTrain_人間 (通常対局) vs 人間 (通常対局) 2026-10-12 05 07 05.sgf")
        is None
    )
    assert detect_my_color("player1", "player2", file_name="player1 vs player2.sgf") is None


def test_names_come_before_rank_and_file_name():
    """The player names in the game are used first, even if the rank and the file name say otherwise."""
    human = katrain_name("人間", "通常対局")
    ai = katrain_name("AI", "人間流")
    file_name = "KaTrain_人間 (通常対局) vs AI (人間流) 2026-10-12 05 07 05.sgf"
    assert detect_my_color(ai, human, ranks=("", "5段"), file_name=file_name) == "W"


def test_recorded_color_comes_first():
    """The color that the user gave is used before my_names and the names in the game."""
    human = katrain_name("人間", "通常対局")
    ai = katrain_name("AI", "人間流")
    assert detect_my_color(human, ai, recorded_color="W") == "W"
    assert detect_my_color("Taro", "opponent", my_names=["Taro"], recorded_color="W") == "W"
    assert detect_my_color("player1", "player2", recorded_color="B") == "B"
    assert detect_my_color(human, ai, recorded_color="") == "B"
