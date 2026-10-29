"""Tests for kentogo.commentary_cli (with a fake AI)."""

from commentary_samples import HUMAN, NOT_ANALYZED, analyzed_game, good_answer

from kentogo import commentary_cli as cli
from kentogo.commentary.history import CommentaryHistory, history_path
from kentogo.commentary.provider_base import Generation, ProviderError
from kentogo.record.ai_comment import AI_HEADER


class FakeProvider:
    """An AI that always gives the same answer."""

    def __init__(self, answer):
        self.answer = answer

    def generate(self, prompt, on_text, cancel):
        on_text(self.answer)
        return Generation(self.answer, 1000, 500)


def run(tmp_path, *arguments):
    """Run the command with a settings file in tmp_path."""
    return cli.main([*map(str, arguments), "--settings", str(tmp_path / "settings.json")])


def test_api(games, tmp_path, monkeypatch, capsys):
    """Through the API, the answer is shown and written, and the game is remembered with its inputs."""
    path = games("a.sgf", analyzed_game())
    monkeypatch.setattr(cli, "make_provider", lambda settings: FakeProvider(good_answer()))
    assert run(tmp_path, path, "--rank", "18k") == 0
    out = capsys.readouterr().out
    assert "the user is black, rank 18k" in out and "Result: done" in out and "Tokens: input 1,000, output 500" in out
    history = CommentaryHistory(history_path(tmp_path / "settings.json"))
    assert (history.entry("a.sgf").my_rank, history.entry("a.sgf").state) == ("18k", "done")
    assert AI_HEADER in path.read_text(encoding="utf-8")


def test_api_errors(games, tmp_path, monkeypatch, capsys):
    """Without a key, or with a bad answer, nothing is written."""
    path = games("a.sgf", analyzed_game())

    def no_key(settings):
        raise ProviderError("no_key", "ANTHROPIC_API_KEY")

    monkeypatch.setattr(cli, "make_provider", no_key)
    assert run(tmp_path, path) == 1
    assert "no_key: ANTHROPIC_API_KEY" in capsys.readouterr().err
    monkeypatch.setattr(cli, "make_provider", lambda settings: FakeProvider("no json"))
    assert run(tmp_path, path) == 1
    assert "error: not_json" in capsys.readouterr().out
    assert AI_HEADER not in path.read_text(encoding="utf-8")


def test_paste_in_two_steps(games, tmp_path, capsys):
    """The prompt is written into a file, and the saved answer is written into the game."""
    path = games("a.sgf", analyzed_game())
    prompt = tmp_path / "prompt.txt"
    assert run(tmp_path, path, "--paste", "--out", prompt) == 0
    assert "# KaTrainの解析データ" in prompt.read_text(encoding="utf-8")
    answer = tmp_path / "answer.txt"
    answer.write_text("Sure!\n" + good_answer(), encoding="utf-8")
    assert run(tmp_path, path, "--paste", "--answer", answer, "--yes") == 0
    assert "Written: moves 1, 3." in capsys.readouterr().out


def test_paste_problems(games, tmp_path, capsys):
    """A game not analyzed, or an answer with errors, writes nothing; the prompt can be shown instead of saved."""
    raw = games("raw.sgf", NOT_ANALYZED)
    assert run(tmp_path, raw, "--paste") == 1
    assert "KaTrain has not analyzed this game" in capsys.readouterr().err
    path = games("a.sgf", analyzed_game())
    answer = tmp_path / "answer.txt"
    answer.write_text(good_answer(moves=(1,)), encoding="utf-8")
    assert run(tmp_path, path, "--paste", "--answer", answer) == 1
    assert "error: missing_move move=3" in capsys.readouterr().out
    assert run(tmp_path, path, "--paste") == 0
    assert "回答の形式" in capsys.readouterr().out


def test_color_and_replacing(games, tmp_path, monkeypatch, capsys):
    """Without a color that can be found, --color is needed; an AI commentary is replaced only if the user agrees."""
    two_humans = games("h.sgf", analyzed_game(HUMAN, HUMAN))
    assert run(tmp_path, two_humans, "--paste") == 2
    assert "--color" in capsys.readouterr().err
    path = games("a.sgf", analyzed_game().replace(";B[ee]C[", f";B[ee]C[{AI_HEADER}\\nold\\n", 1))
    monkeypatch.setattr("builtins.input", lambda question: "n")
    assert run(tmp_path, path, "--paste") == 1
    assert "Nothing was changed." in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda question: "y")
    assert run(tmp_path, path, "--paste", "--color", "B") == 0


def test_answer_file_missing_or_with_bom(games, tmp_path, capsys):
    """A missing answer file is told in one line; a UTF-8 file with a BOM (as saved by Notepad) is read."""
    path = games("a.sgf", analyzed_game())
    assert run(tmp_path, path, "--paste", "--answer", tmp_path / "none.txt") == 1
    assert "The answer file cannot be read" in capsys.readouterr().err
    answer = tmp_path / "answer.txt"
    answer.write_text(good_answer(), encoding="utf-8-sig")
    assert run(tmp_path, path, "--paste", "--answer", answer) == 0
