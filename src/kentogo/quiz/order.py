"""Put the problems in the order chosen in the settings, and keep one problem for each position."""

from __future__ import annotations

import os
import random
from collections.abc import Callable
from pathlib import Path

from kentogo.mistakes.problem import Problem
from kentogo.quiz.quiz_settings import ORDER_FILE_NAME, ORDER_NEWEST, ORDER_RANDOM


def order_problems(
    problems: list[Problem],
    order: str,
    rng: random.Random,
    modified_time: Callable[[str], float] = os.path.getmtime,
) -> list[Problem]:
    """Return the problems in the given order.

    With ORDER_FILE_NAME and ORDER_NEWEST, the problems of one game stay together,
    in the order they had (from the largest loss to the smallest).

    Args:
        problems: The problems.
        order: ORDER_FILE_NAME, ORDER_NEWEST or ORDER_RANDOM.
        rng: The random number generator, used for ORDER_RANDOM.
        modified_time: Returns the time when a file was last changed. Tests pass a fake one.

    Returns:
        A new list with the problems in order.

    Raises:
        ValueError: If the order is unknown.
    """
    if order == ORDER_FILE_NAME:
        return sorted(problems, key=lambda problem: Path(problem.sgf_path).name)
    elif order == ORDER_NEWEST:
        times = {path: modified_time(path) for path in {problem.sgf_path for problem in problems}}
        return sorted(problems, key=lambda problem: -times[problem.sgf_path])
    elif order == ORDER_RANDOM:
        mixed = list(problems)
        rng.shuffle(mixed)
        return mixed
    else:
        raise ValueError(f"unknown order: {order!r}")


def keep_newest(problems: list[Problem], modified_time: Callable[[str], float] = os.path.getmtime) -> list[Problem]:
    """When the same position is in more than one SGF file, keep only the problem from the newest file.

    For example a game saved twice, or saved again after it was analyzed again.
    The problems that are kept stay in their order.

    Args:
        problems: The problems.
        modified_time: Returns the time when a file was last changed. Tests pass a fake one.

    Returns:
        A new list with one problem for each problem ID.
    """
    times: dict[str, float] = {}
    for path in {problem.sgf_path for problem in problems}:
        try:
            times[path] = modified_time(path)
        except OSError:
            times[path] = 0.0  # A file that cannot be read now counts as the oldest.
    newest: dict[str, Problem] = {}
    for problem in problems:
        kept = newest.get(problem.problem_id)
        if kept is None or times[problem.sgf_path] > times[kept.sgf_path]:
            newest[problem.problem_id] = problem
    return [problem for problem in problems if newest[problem.problem_id] is problem]
