"""Tests for kentogo.commentary.batch (with a fake AI)."""

import threading

from commentary_samples import NOT_ANALYZED, analyzed_game, good_answer

from kentogo.commentary.batch import (
    STATUS_BAD_ANSWER,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_NOT_ANALYZED,
    STATUS_NOTHING,
    BatchListener,
    run_batch,
    run_listed_games,
)
from kentogo.commentary.history import STATE_DONE, STATE_PENDING, CommentaryHistory, GameEntry
from kentogo.commentary.job import GameRequest
from kentogo.commentary.prompt_text import default_prompt_text
from kentogo.commentary.provider_base import Generation, ProviderError
from kentogo.common import sgf
from kentogo.mistakes.extract import ExtractSettings
from kentogo.record.ai_comment import split_ai_comment


class FakeProvider:
    """An AI that gives prepared answers in order, and remembers the prompts."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def generate(self, prompt, on_text, cancel):
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        on_text(answer[:5])
        return Generation(answer, 100, 50)


def request(path, rank="18k"):
    """Ask for the commentary of a game for black."""
    return GameRequest(path, "B", rank, "same")


def test_games_are_written_and_remembered(games):
    """Each game gets its commentary, the history is updated, and the screen is told what happens."""
    a = games("a.sgf", analyzed_game())
    b = games("b.sgf", analyzed_game())
    history = CommentaryHistory(":memory:")
    events = []
    listener = BatchListener(
        on_start=lambda i, n, r: events.append(("start", i, n, r.name)),
        on_text=lambda text: events.append(("text", text)),
        on_finish=lambda outcome: events.append(("finish", outcome.status)),
    )
    provider = FakeProvider(good_answer(), good_answer())
    outcomes = run_listed_games(
        [request(a), request(b, "17k")], provider, default_prompt_text(), history, listener, clock=lambda: 5_000
    )
    assert [o.status for o in outcomes] == [STATUS_DONE, STATUS_DONE]
    assert events[0] == ("start", 0, 2, "a.sgf") and events[2] == ("finish", STATUS_DONE)
    assert outcomes[0].backup.exists() and outcomes[0].generation.input_tokens == 100
    assert "段級位: 17級" in provider.prompts[1].user
    comment = str(sgf.main_line(sgf.load_game(a))[1].get_property("C"))
    assert split_ai_comment(comment).move_text.startswith("(実戦 E5 → 最善 C3,損失 4.0目)")
    entry = history.entry("b.sgf")
    assert (entry.state, entry.my_rank, entry.done_modified_ns) == (STATE_DONE, "17k", b.stat().st_mtime_ns)
    assert history.since_ns() == 5_000


def test_problems_make_games_pending(games):
    """Games not analyzed, failed, or with a bad answer are pending, and do not stop the others."""
    raw = games("raw.sgf", NOT_ANALYZED)
    bad = games("bad.sgf", analyzed_game())
    fail = games("fail.sgf", analyzed_game())
    good = games("good.sgf", analyzed_game())
    history = CommentaryHistory(":memory:")
    provider = FakeProvider('{"moves": []}', ProviderError("credit", "no credit"), good_answer())
    requests = [request(raw), request(bad), request(fail), request(good)]
    outcomes = run_listed_games(requests, provider, default_prompt_text(), history, not_analyzed=["other.sgf"])
    assert [o.status for o in outcomes] == [STATUS_NOT_ANALYZED, STATUS_BAD_ANSWER, STATUS_FAILED, STATUS_DONE]
    assert outcomes[1].answer_text == '{"moves": []}' and outcomes[1].problems
    assert (outcomes[2].detail, outcomes[2].error_kind) == ("no credit", "credit")
    states = {name: history.entry(name).state for name in ("raw.sgf", "bad.sgf", "fail.sgf", "good.sgf", "other.sgf")}
    assert states == {
        "raw.sgf": STATE_PENDING,
        "bad.sgf": STATE_PENDING,
        "fail.sgf": STATE_PENDING,
        "good.sgf": STATE_DONE,
        "other.sgf": STATE_PENDING,
    }
    assert history.entry("bad.sgf") == GameEntry("bad.sgf", "B", "18k", "same", STATE_PENDING)
    assert list(games.folder.glob("bad.sgf.*.bak")) == []  # Nothing was written.


def test_cancel(games):
    """After cancel, the current game is not written and the rest are not started; all of them stay pending."""
    a = games("a.sgf", analyzed_game())
    b = games("b.sgf", analyzed_game())
    cancel = threading.Event()

    class CancellingProvider(FakeProvider):
        def generate(self, prompt, on_text, cancel_event):
            cancel.set()  # The user presses cancel while the AI answers.
            return super().generate(prompt, on_text, cancel_event)

    history = CommentaryHistory(":memory:")
    provider = CancellingProvider(good_answer(), good_answer())
    outcomes = run_batch([request(a), request(b)], provider, default_prompt_text(), history, cancel=cancel)
    assert [o.status for o in outcomes] == [STATUS_CANCELLED, STATUS_CANCELLED]
    assert len(provider.prompts) == 1 and list(games.folder.glob("*.bak")) == []
    assert history.entry("a.sgf").state == history.entry("b.sgf").state == STATE_PENDING


def test_without_history(games):
    """Without the history, the games are still written."""
    a = games("a.sgf", analyzed_game())
    outcomes = run_batch([request(a)], FakeProvider(good_answer()), default_prompt_text(), None)
    assert outcomes[0].status == STATUS_DONE


def test_one_game_keeps_the_time(games):
    """run_batch alone (for a game not from the list) does not move the time from which games are shown."""
    a = games("a.sgf", analyzed_game())
    history = CommentaryHistory(":memory:")
    history.set_since_ns(1_000)
    run_batch([request(a)], FakeProvider(good_answer()), default_prompt_text(), history)
    assert history.since_ns() == 1_000


def test_a_game_with_nothing_to_explain(games):
    """When no move meets the quiz's conditions, the AI is not asked, and the game is not listed again."""
    path = games("a.sgf", analyzed_game())
    history = CommentaryHistory(":memory:")
    provider = FakeProvider()
    conditions = ExtractSettings(min_points_lost=10.0)  # Moves 1 and 3 lose 4 and 6 points.
    outcome = run_batch([request(path)], provider, default_prompt_text(), history, conditions=conditions)[0]
    assert outcome.status == STATUS_NOTHING and provider.prompts == []
    entry = history.entry("a.sgf")
    assert entry.state == STATE_DONE and entry.done_modified_ns == path.stat().st_mtime_ns
