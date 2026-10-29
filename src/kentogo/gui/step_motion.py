"""How the stones move when a step of the computer's seichi is shown, without Kivy (so that it can be tested).

A step moves stones as a person would: a stone slides from its point (or from the tray of
prisoners) to its new point, and is put there. This module tells which stones move in a
step, and where a moving stone is at a moment of the move.
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.seichi.arrangement import FillStep

Point = tuple[int, int]


@dataclass(frozen=True)
class StoneMotion:
    """A stone that moves in a step.

    Attributes:
        color: The color of the stone while it moves (an exchanged stone changes when it is put).
        source: The point it comes from, or None for a prisoner from the tray of its color.
        target: The point it is put on.
    """

    color: str
    source: Point | None
    target: Point


def step_motions(step: FillStep) -> tuple[StoneMotion, ...]:
    """Return the stones that move in a step.

    A prisoner put into the territory comes from its tray. A moved stone, and a stone moved
    and exchanged, slide from their point. In a swap, the two stones pass each other. Stones
    taken off, and a stone only changed to the other color, do not move.
    """
    points = step.points
    if step.kind == "place" and len(points) == 1:
        return (StoneMotion(step.color, None, points[0]),)
    if step.kind not in ("move", "exchange", "swap") or len(points) != 2:
        return ()
    source, target = points
    first = StoneMotion(step.color, source, target)
    if step.kind != "swap":
        return (first,)
    other = step.stones.get(source, "W" if step.color == "B" else "B")
    return (first, StoneMotion(other, target, source))


def without_moving(stones: dict[Point, str], motions: tuple[StoneMotion, ...]) -> dict[Point, str]:
    """Return the stones after a step without the stones that are still moving to their points."""
    targets = {motion.target for motion in motions}
    return {point: color for point, color in stones.items() if point not in targets}


def eased(fraction: float) -> float:
    """Return how far a stone has gone at a moment of its move (0 to 1): it starts and stops gently."""
    t = min(max(fraction, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def between(start: tuple[float, float], end: tuple[float, float], fraction: float) -> tuple[float, float]:
    """Return the place of a moving stone at a moment of its move (fraction 0: start, 1: end)."""
    t = eased(fraction)
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
