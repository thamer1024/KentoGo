"""Tests for kentogo.commentary.prompt."""

from kentogo.commentary.language import CommentaryLanguage
from kentogo.commentary.material import GameMaterial, GroupInfo, MoveMaterial, OpponentReply, PvStep
from kentogo.commentary.prompt import PlayerInfo, build_prompt, loss_table
from kentogo.commentary.prompt_text import PromptText, default_prompt_text
from kentogo.commentary.prompt_words import ENGLISH_WORDS, JAPANESE_WORDS
from kentogo.common.types import Move
from kentogo.record.game_record import BoardState

BEFORE = BoardState({(1, 0): "B", (0, 0): "W"}, {"B": 0, "W": 0})
AFTER = BoardState({(1, 0): "B", (0, 1): "B", (2, 2): "W"}, {"B": 1, "W": 0})

MOVE = MoveMaterial(
    number=3,
    played=Move.from_gtp("G7", "B"),
    points_lost=6.0,
    best_move=Move.from_gtp("A2", "B"),
    before=BEFORE,
    last_move=Move.from_gtp("A1", "W"),
    pv=(Move.from_gtp("A2", "B"), Move.from_gtp("C3", "W")),
    pv_steps=(
        PvStep(Move.from_gtp("A2", "B"), ((0, 0),), ()),
        PvStep(Move.from_gtp("C3", "W"), (), (GroupInfo("B", ((0, 1), (1, 0)), 1),)),
    ),
    after_pv=AFTER,
    nearby=(GroupInfo("W", ((0, 0),), 1),),
    candidates=(("A2", 0.0), ("G7", 6.0)),
    score_after=-4.0,
    reply=OpponentReply(Move.from_gtp("C3", "W"), 2.0, "D4", (Move.from_gtp("D4", "W"),)),
    notes="my note",
    katrain_text="Move 3: B G7\nPolicy rank 8",
)
MATERIAL = GameMaterial(9, 6.5, "B", (MOVE,), ((20, 0), (12, 0), (10, 0), (8, 0), (6, 1), (3, 1)), 6)
PLAYER = PlayerInfo("18級", "same")
TEXT = PromptText("ROLE", "INTRO {color}", "- weak point\n\n- goal", "1. RULE")


def test_prompt_parts():
    """The parts from the prompt file come first, with the user's color, rank and opponent."""
    prompt = build_prompt(MATERIAL, PLAYER, TEXT)
    assert prompt.system == "ROLE"
    assert prompt.user.startswith(
        "INTRO 黒\n\n# 私について\n- 段級位: 18級(この対局の時点)\n- weak point\n- goal\n"
        "- この対局の相手: 同ランク(互先)\n\n# 守ること(最重要)\n1. RULE\n\n# 盤面図の見方"
    )
    assert '"what_happened"' in prompt.user and "| 6目以上 | 1回 | 5 | 11 |" in prompt.user


def test_move_facts():
    """Each move has the facts worked out by KentoGo and the diagrams."""
    text = build_prompt(MATERIAL, PLAYER, TEXT).user
    assert "## 第3手目(黒番)\n- 実戦の手: 黒G7,損失: 6.0目\n- AIの最善手: A2\n- 相手の直前の手: 白A1" in text
    assert "- 候補手(損失の小さい順): A2(0.0目),G7(6.0目)" in text
    assert "- この手の後の形勢: 白が約4.0目リード" in text
    assert "予想手順の1手目 黒A2: 白の石 A1(1子)を取る" in text
    assert "予想手順の2手目 白C3: 黒の石 A2,B1(2子)がアタリになる" in text
    assert "  白の石 A1(1子): ダメ1" in text
    assert "- 相手の手番での最善手: D4(相手の実戦の手の損失 2.0目)" in text
    assert "- 私のメモ: my note\n- KaTrainの元コメント:\nMove 3: B G7\nPolicy rank 8" in text
    assert "- 拡大図:" in text and "- 予想手順の後の盤面図:" in text


def test_paste_text_and_default_parts():
    """The paste text has the system prompt, the message and the reminder. The default file can be used."""
    prompt = build_prompt(MATERIAL, PlayerInfo(), default_prompt_text())
    assert prompt.for_paste() == f"{prompt.system}\n\n{prompt.user}\n\n{JAPANESE_WORDS.paste_reminder}"
    assert "- 段級位:" not in prompt.user and "この対局の相手: 指定なし" in prompt.user
    assert "私は黒番です" in prompt.user and "KentoGoが計算した事実" in prompt.user


def test_loss_table_without_targets():
    """Without a rank in the table, the counts are given without targets."""
    table = loss_table(MATERIAL, "", JAPANESE_WORDS)
    assert "| 3目以上 | 1回 | - | - |" in table and "目標との比較はありません" in table


ENGLISH = CommentaryLanguage("en", "German")


def test_the_japanese_prompt_asks_for_the_categories_by_their_english_names():
    """The AI answers with the names of language.CATEGORIES, which the Japanese prompt shows with their words."""
    text = build_prompt(MATERIAL, PLAYER, TEXT).user
    assert "missed_urgent_point(急場の見逃し)/no_pressure(響かない手)" in text and "German" not in text
    # Japanese is asked even when the rules of the user's prompt file do not ask for it.
    assert "で入れる.\n- JSONの文章はすべて日本語で書く.\n\n# この対局の損失の回数" in text


def test_english_prompt():
    """The English prompt has KentoGo's parts in English, and asks for the answer in the language of the screens."""
    prompt = build_prompt(
        MATERIAL, PlayerInfo("18k", "lower"), PromptText("ROLE", "I played {color}.", "", "", ENGLISH)
    )
    assert prompt.user.startswith(
        "I played Black.\n\n# About me\n- Rank: 18 kyu (at the time of this game)\n"
        "- Opponent in this game: one rank below me\n\n# Rules (most important)"
    )
    assert "- Write all the texts of the JSON in German." in prompt.user
    assert "## Move 3 (Black)\n- Move played: Black G7, loss: 6.0 points\n- AI's best move: A2" in prompt.user
    assert "Move 1 of the predicted sequence, Black A2: captures White stones A1 (count: 1)" in prompt.user
    assert "| 6+ points | 1 | 5 | 11 |" in prompt.user and "黒" not in prompt.user
    assert prompt.for_paste().endswith(ENGLISH_WORDS.paste_reminder)


def test_default_english_prompt():
    """The default English prompt file can be used, and has no Japanese words."""
    prompt = build_prompt(MATERIAL, PlayerInfo(), default_prompt_text(ENGLISH))
    assert "I played Black." in prompt.user and "Facts worked out by KentoGo" in prompt.user
    assert not any("\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff" for char in prompt.for_paste())
