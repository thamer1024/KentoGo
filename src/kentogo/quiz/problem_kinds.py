"""Which kinds of problems are asked: all of them, or only the punishment problems.

A punishment problem is a mistake right after the opponent's big mistake, when the opponent's
mistake made a new chance that the user missed (see mistakes.extract.PunishmentChance). Asking
only them trains finding the move that punishes the opponent. Then every punishment problem of a
game is asked, also those beyond the problems of the game (problems_per_game; see problems_of_kind).
"""

from __future__ import annotations

from collections.abc import Iterable

from kentogo.mistakes.extract import PUNISH, ExtractResult
from kentogo.mistakes.problem import Problem

KIND_ALL = "all"  # Every problem.
KIND_PUNISH = "punish"  # Only the punishment problems.
PROBLEM_KINDS = (KIND_ALL, KIND_PUNISH)


def other_kinds(problems: Iterable[Problem], kind: str) -> set[str]:
    """Return the IDs of the problems that are not of the kind asked (none for KIND_ALL)."""
    if kind == KIND_ALL:
        return set()
    return {problem.problem_id for problem in problems if problem.punishment != PUNISH}


def problems_of_kind(results: Iterable[ExtractResult], kind: str) -> list[Problem]:
    """Return the problems of the games: for KIND_PUNISH, with the punishment problems beyond them."""
    problems = []
    for result in results:
        problems += result.problems
        if kind == KIND_PUNISH:
            problems += result.punishments
    return problems
