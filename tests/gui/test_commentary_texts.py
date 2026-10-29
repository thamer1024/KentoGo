"""Tests for kentogo.gui.commentary_texts."""

from pathlib import Path

from kentogo.commentary.answer import AnswerProblem
from kentogo.commentary.batch import STATUS_BAD_ANSWER, STATUS_DONE, STATUS_FAILED, GameOutcome
from kentogo.commentary.job import GameRequest
from kentogo.commentary.language import PROMPT_ENGLISH, PROMPT_JAPANESE, CommentLabels
from kentogo.commentary.prompt_text import PromptFileProblem
from kentogo.commentary.provider_base import ERROR_NO_KEY, Generation
from kentogo.commentary.sgf_writer import WriteResult
from kentogo.gui import texts
from kentogo.gui.commentary_texts import (
    ANSWER_LANGUAGES,
    COLORS,
    RANK_CHOICES,
    RELATION_CHOICES,
    answer_problems_text,
    color_label,
    comment_labels,
    commentary_language,
    outcome_text,
    players_text,
    prompt_file_problems_text,
    provider_error_text,
    rank_label,
    relation_label,
    status_text,
    tokens_text,
    written_text,
)
from kentogo.record.ai_comment import AI_HEADER_EN


def test_choices():
    """The choices start with "not given", and the ranks go from the strongest."""
    assert COLORS == ("", "B", "W")
    assert (RANK_CHOICES[0], RANK_CHOICES[1], RANK_CHOICES[-1]) == ("", "9d", "20k")
    assert RELATION_CHOICES[-1] == ""


def test_labels():
    """The labels are in the language of the screens."""
    assert (color_label("B"), color_label("")) == ("黒", "選んでください")
    assert (rank_label("18k"), rank_label("3d"), rank_label("")) == ("18級", "3段", "指定なし")
    assert (relation_label("higher"), relation_label("")) == ("1つ上", "指定なし")


def test_messages():
    """The problems of the answer and of the prompt file, and the message after writing, are written out."""
    problems = (AnswerProblem("missing_move", move=5), AnswerProblem("empty_field", field="main_issue"))
    assert answer_problems_text(problems) == "・5手目の解説がありません\n・総評の「main_issue」が空です"
    file_problem = PromptFileProblem(Path("p.txt"), "missing", "rules")
    assert prompt_file_problems_text([file_problem]) == "p.txt に [[rules]] がないため、その部分は標準の内容を使います"
    assert written_text(WriteResult(Path("g.sgf.bak"), (3, 5))).startswith("棋譜に書き込みました（3, 5手目）。")


REQUEST = GameRequest(Path("game.sgf"), "B", "5k", "same")


def test_provider_error_text():
    """Each kind of error has its message; a missing key names the variable, and an unknown kind is "other"."""
    assert "MY_KEY" in provider_error_text(ERROR_NO_KEY, "", "MY_KEY")
    assert "boom" in provider_error_text("strange", "boom", "MY_KEY")


def test_tokens_text():
    """The numbers of tokens are shown, with a warning when the answer was cut."""
    assert tokens_text(Generation("a", 10, 20)) == "入力 10 トークン / 出力 20 トークン"
    assert "途切れ" in tokens_text(Generation("a", 10, 20, truncated=True))


def test_status_and_outcome_texts():
    """A written game tells the backup and the tokens; a failure tells why; errors of the answer are listed."""
    done = GameOutcome(REQUEST, STATUS_DONE, generation=Generation("a", 1, 2), backup=Path("game.sgf.bak"))
    assert status_text(done, "K") == "書き込みました"
    assert "game.sgf.bak" in outcome_text(done, "K") and "出力 2 トークン" in outcome_text(done, "K")
    failed = GameOutcome(REQUEST, STATUS_FAILED, "", ERROR_NO_KEY)
    assert "K" in status_text(failed, "K")
    assert status_text(GameOutcome(REQUEST, STATUS_FAILED, "broken"), "K") == "失敗: broken"
    bad = GameOutcome(REQUEST, STATUS_BAD_ANSWER, problems=(AnswerProblem("missing_move", 3),))
    assert "3手目の解説がありません" in outcome_text(bad, "K")


def test_players_text():
    """The players and the result are shown, with "?" for an unknown name."""
    assert players_text("A", "", "B+R") == "黒 A / 白 ?　B+R"


def test_the_commentary_follows_the_language_of_the_screens():
    """Japanese uses the Japanese prompt; the other languages use the English one and ask for their language."""
    assert set(ANSWER_LANGUAGES) == set(texts.LANGUAGES)
    try:
        texts.set_language("jp")
        assert commentary_language().prompt == PROMPT_JAPANESE
        # The Japanese words of the screens are the default words of the SGF file (used without screens).
        assert comment_labels(PROMPT_JAPANESE) == CommentLabels()
        texts.set_language("de")
        language = commentary_language()
        assert (language.prompt, language.answer) == (PROMPT_ENGLISH, "German")
        assert language.labels.black == "Schwarz" and language.labels.category_name("misread") == "Falsch gelesen"
        assert language.labels.move_header == AI_HEADER_EN
    finally:
        texts.set_language(texts.DEFAULT_LANGUAGE)
