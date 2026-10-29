"""Tests for kentogo.commentary.paste."""

import pytest
from commentary_samples import NOT_ANALYZED, analyzed_game, good_answer

from kentogo.commentary.history import STATE_DONE, STATE_PENDING, CommentaryHistory
from kentogo.commentary.job import GameRequest, NotAnalyzedError
from kentogo.commentary.paste import apply_paste, prepare_paste, remember_not_analyzed
from kentogo.commentary.prompt_text import default_prompt_text
from kentogo.commentary.prompt_words import JAPANESE_WORDS


def test_paste_a_good_answer(games):
    """The prompt is made for copying, and a good answer is written and remembered."""
    path = games("a.sgf", analyzed_game())
    history = CommentaryHistory(":memory:")
    prepared = prepare_paste(GameRequest(path, "B", "18k", "same"), default_prompt_text())
    assert prepared.asked_moves == [1, 3]
    assert prepared.prompt.for_paste().endswith(JAPANESE_WORDS.paste_reminder)
    result = apply_paste(prepared, "Here you are:\n" + good_answer(), history)
    assert result.answer.ok and result.written.moves == (1, 3) and result.error == ""
    assert history.entry("a.sgf").state == STATE_DONE


def test_paste_a_bad_answer_writes_nothing(games):
    """An answer with errors is not written, so that the user can paste again."""
    path = games("a.sgf", analyzed_game())
    history = CommentaryHistory(":memory:")
    prepared = prepare_paste(GameRequest(path, "B"), default_prompt_text())
    result = apply_paste(prepared, good_answer(moves=(1,)), history)
    assert not result.answer.ok and result.written is None
    assert list(games.folder.glob("*.bak")) == [] and history.entry("a.sgf") is None
    assert apply_paste(prepared, good_answer(), history).written is not None  # Pasted again, correctly.


def test_paste_a_game_not_analyzed(games):
    """A game that KaTrain has not analyzed has no prompt, and is remembered as pending."""
    path = games("raw.sgf", NOT_ANALYZED)
    request = GameRequest(path, "B", "18k")
    with pytest.raises(NotAnalyzedError):
        prepare_paste(request, default_prompt_text())
    history = CommentaryHistory(":memory:")
    remember_not_analyzed(request, history)
    assert history.entry("raw.sgf").state == STATE_PENDING
    remember_not_analyzed(request, None)  # Without the history, nothing happens.


def test_file_changed_before_pasting(games):
    """If the moves of the file change before the answer is pasted, nothing is written and the reason is told."""
    path = games("a.sgf", analyzed_game())
    prepared = prepare_paste(GameRequest(path, "B"), default_prompt_text())
    path.write_text(analyzed_game().replace(";B[gc]", ";B[gd]"), encoding="utf-8")
    result = apply_paste(prepared, good_answer(), None)
    assert result.written is None and "changed" in result.error
