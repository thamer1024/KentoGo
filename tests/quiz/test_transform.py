"""Tests for kentogo.quiz.transform."""

import random

import pytest

from kentogo.common.board import Board
from kentogo.common.types import Move, Position
from kentogo.katago.estimate import Estimate, Standing
from kentogo.mistakes.problem import Problem, Variation
from kentogo.quiz.transform import IDENTITY, SYMMETRIES, BoardTransform, random_transform

SIZE = 19
Q16 = Move.from_gtp("Q16", "B")


def all_transforms():
    """Return all 16 changes (8 symmetries, with and without swapping colors)."""
    return [BoardTransform(s, swap) for s in SYMMETRIES for swap in (False, True)]


def test_identity_changes_nothing():
    """Symmetry 0 without swapping colors keeps every move."""
    assert IDENTITY.move(Q16, SIZE) == Q16


def test_rotation_by_90_degrees():
    """One rotation moves Q16 (upper right) to another corner, and four rotations bring it back."""
    moved = BoardTransform(1).move(Q16, SIZE)
    assert moved.gtp() in {"Q4", "D16"}
    point = Q16.coord
    for _ in range(4):
        point = BoardTransform(1).point(point, SIZE)
    assert point == Q16.coord


def test_flip_left_to_right():
    """Symmetry 4 is a flip left to right."""
    assert BoardTransform(4).move(Q16, SIZE).gtp() == "D16"


def test_the_8_symmetries_are_different():
    """A point that is not on a line of symmetry goes to 8 different places."""
    point = Move.from_gtp("R14", "B").coord
    assert len({BoardTransform(s).point(point, SIZE) for s in SYMMETRIES}) == 8


@pytest.mark.parametrize("transform", all_transforms())
def test_inverse_brings_the_move_back(transform):
    """inverse() undoes every change, including the color swap."""
    move = Move.from_gtp("R14", "W")
    assert transform.inverse().move(transform.move(move, SIZE), SIZE) == move


def test_swap_colors():
    """Swapping colors changes the color of moves and the player to move."""
    position = Position(SIZE, 6.5, "japanese", (Move.from_gtp("D4", "B"),), (Q16,), "W")
    changed = BoardTransform(0, swap_colors=True).position(position)
    assert changed.setup[0].color == "W"
    assert changed.moves[0].color == "W"
    assert changed.next_color == "B"


def test_pass_stays_a_pass():
    """A pass has no point, so it stays a pass."""
    assert BoardTransform(3).move(Move("B", None), SIZE).is_pass


@pytest.mark.parametrize("transform", all_transforms())
def test_changed_position_has_the_same_capture(transform):
    """After a change, the same stone is captured, at the changed point."""
    text = "B:E5 W:E6 B:A1 W:E4 B:A2 W:D5 B:A3 W:F5"
    moves = tuple(Move.from_gtp(item[2:], item[0]) for item in text.split())
    position = Position(9, 6.5, "japanese", (), moves, "B")
    board = Board.from_position(transform.position(position))
    captured = transform.move(Move.from_gtp("E5", "B"), 9)
    assert board.stone_at(captured.coord) is None
    assert sum(board.captures.values()) == 1
    assert len(board.stones()) == len(moves) - 1


def test_problem_is_changed_but_keeps_its_id_and_notes():
    """All moves of a problem are changed, and the ID and notes stay the same."""
    problem = Problem(
        problem_id="abc",
        sgf_path="game.sgf",
        move_number=2,
        position=Position(SIZE, 6.5, "japanese", (), (Q16,), "W"),
        actual_move=Move.from_gtp("A1", "W"),
        best_move=Move.from_gtp("D4", "W"),
        points_lost=5.0,
        variations=(Variation((Move.from_gtp("D4", "W"), Move.from_gtp("Q4", "B")), "katrain"),),
        notes="D4 is better",
    )
    transform = BoardTransform(4)
    changed = transform.problem(problem)
    assert (changed.problem_id, changed.notes) == ("abc", "D4 is better")
    assert changed.actual_move == transform.move(problem.actual_move, SIZE)
    assert changed.best_move == transform.move(problem.best_move, SIZE)
    assert changed.variations[0].moves == transform.moves(problem.variations[0].moves, SIZE)
    assert changed.position.moves == transform.moves(problem.position.moves, SIZE)


def test_random_transform():
    """Random changes use only what is allowed, and a fixed seed gives the same result."""
    assert random_transform(random.Random(1)) == random_transform(random.Random(1))
    rng = random.Random(2)
    assert all(random_transform(rng, rotate=False) == IDENTITY for _ in range(20))
    chosen = {random_transform(rng, swap_colors=True) for _ in range(200)}
    assert len(chosen) == 16


def test_the_standing_follows_the_board():
    """Turned and with the colors swapped, the owners move and change sides, and so does the lead."""
    standing = Standing(Estimate(2.0, {(0, 0): 1.0}), Estimate(1.0, {}), "B")
    shown = BoardTransform(symmetry=4, swap_colors=True).standing(standing, 3)
    assert shown.end.ownership == {(2, 0): -1.0} and shown.end.lead == -2.0 and shown.color == "W"
    assert shown.gain == standing.gain
    assert BoardTransform().standing(standing, 3) == standing
