"""Tests for kentogo.punishment_cli (the list of moments when the user did not punish a mistake)."""

import json

from kentogo import punishment_cli
from kentogo.record.katrain_comment import INTERNAL_MARKER
from kentogo.settings_file import load_settings

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def comment(number: int, color: str, point: str, loss: float) -> str:
    return f"\nMove {number}: {color} {point}\nEstimated point loss: {loss:.1f}\nPredicted top move was Q4 (B+1.0).\n{INTERNAL_MARKER}"


GAME = (
    f"(;SZ[19]PB[{HUMAN}]PW[{AI}];B[pd]C[{comment(1, 'B', 'Q16', 1.0)}];W[aa]C[{comment(2, 'W', 'A19', 20.0)}]"
    f";B[ab]C[{comment(3, 'B', 'A18', 15.0)}])"
)


def test_list_the_moments_of_the_games_folder(tmp_path, monkeypatch, capsys):
    games = tmp_path / "games"
    games.mkdir()
    (games / "game.sgf").write_text(GAME, encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"quiz": {"games_folder": str(games)}}), encoding="utf-8")
    monkeypatch.setattr(punishment_cli, "load_settings", lambda path: load_settings(path, tmp_path / "none.json"))
    assert punishment_cli.main(["--settings", str(settings)]) == 0
    output = capsys.readouterr().out
    assert (
        "move   3 shared: after W A19  lost  20.0 (best Q4  ), you played A18  lost  15.0; best Q4  problem" in output
    )
    assert "Done: 1 moments in 1 games (punish 0, shared 1; decided 0)." in output
    assert punishment_cli.main(["--settings", str(settings), "--opponent-loss", "25"]) == 0
    assert "Done: 0 moments" in capsys.readouterr().out
