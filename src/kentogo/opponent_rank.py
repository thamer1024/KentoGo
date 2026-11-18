"""The ranks of the players, for the human-like moves of KataGo's sequences of the quiz (see quiz.human_line).

The opponent plays as the model it was (KataGo's human-like model) at its rank: the opponent's rank in the
SGF file (KaTrain writes the rank of its AI, such as "10級"), else the user's rank. The user's rank is the
one in the SGF file (games from servers such as Fox Weiqi have both), else the rank that the user gave for
the AI commentary of the game (else the last rank given), and else the opponent's rank (the user's moves are
human-like too, except in the comparison model's sequence). Without any, KataGo's own sequences are shown.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kentogo.commentary.targets import normalize_rank
from kentogo.commentary_inputs import given_rank
from kentogo.common.sgf import load_game
from kentogo.common.types import opponent
from kentogo.mistakes.local_fight import LocalFight
from kentogo.mistakes.problem import Problem
from kentogo.quiz.human_line import PlayerRanks


def player_ranks(sgf_path: str, my_color: str, given_rank: Callable[[str], str]) -> PlayerRanks:
    """Return the ranks of the players for the human-like moves of KataGo's sequences ("" if not known).

    Args:
        sgf_path: The SGF file of the problem.
        my_color: The user's color.
        given_rank: Returns the rank that the user gave for a file name (for the AI commentary), or "".
    """
    try:
        root = load_game(sgf_path)
        ranks = {color: normalize_rank(str(root.get_property(f"{color}R", ""))) for color in ("B", "W")}
    except Exception:  # A file that cannot be read any more: only the given rank is left.
        ranks = {}
    mine = ranks.get(my_color) or normalize_rank(given_rank(Path(sgf_path).name))
    return PlayerRanks(mine, ranks.get(opponent(my_color)) or mine)


def problem_ranks(settings_path: Path, problem: Problem) -> PlayerRanks:
    """Return the ranks of the players of a problem's game (the user plays the problem's next move)."""
    return player_ranks(problem.sgf_path, problem.position.next_color, lambda name: given_rank(settings_path, name))


def fight_ranks(settings_path: Path, fight: LocalFight) -> PlayerRanks:
    """Return the ranks of the players of a local fight's game (the user plays the fight's next move)."""
    return player_ranks(fight.sgf_path, fight.position.next_color, lambda name: given_rank(settings_path, name))
