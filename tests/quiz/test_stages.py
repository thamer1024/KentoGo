"""Tests for kentogo.quiz.stages."""

from dataclasses import dataclass

import pytest

from kentogo.quiz.stages import NO_STAGES, StageStatus, current_stage, held_back, parse_stages

STAGES = (20.0, 10.0, 5.0, 3.0)


@dataclass(frozen=True)
class Item:
    """A problem: only an ID and a loss."""

    problem_id: str
    points_lost: float


ITEMS = [Item("a25", 25.0), Item("b20", 20.0), Item("c12", 12.0), Item("d6", 6.0), Item("e3", 3.0)]


def test_parse_stages_sorts_and_drops_repeats():
    assert parse_stages("5, 20,10,5、3") == STAGES


def test_parse_stages_empty_means_no_stages():
    assert parse_stages("") == ()
    assert parse_stages(" , ") == ()


@pytest.mark.parametrize("text", ["20,abc", "20,0", "-5"])
def test_parse_stages_rejects_wrong_values(text):
    with pytest.raises(ValueError):
        parse_stages(text)


def test_first_stage_until_its_problems_are_answered():
    assert current_stage(ITEMS, {"a25"}, STAGES) == StageStatus(20.0, 0, 4, 1)


def test_next_stage_after_every_problem_of_the_stage_is_answered():
    assert current_stage(ITEMS, {"a25", "b20"}, STAGES) == StageStatus(10.0, 1, 4, 1)


def test_new_big_mistake_brings_the_first_stage_back():
    items = [*ITEMS, Item("f30", 30.0)]
    assert current_stage(items, {"a25", "b20", "c12"}, STAGES) == StageStatus(20.0, 0, 4, 1)


def test_last_stage_when_everything_is_answered():
    answered = {item.problem_id for item in ITEMS}
    assert current_stage(ITEMS, answered, STAGES) == StageStatus(3.0, 3, 4, 0)


def test_no_stages():
    assert current_stage(ITEMS, set(), ()) == NO_STAGES
    assert held_back(ITEMS, {"e3"}, NO_STAGES) == set()


def test_held_back_only_new_problems_below_the_threshold():
    """c12 and d6 were answered before (not new), and a25 is new but in the stage: only e3 waits."""
    assert held_back(ITEMS, {"a25", "e3"}, StageStatus(20.0, 0, 4, 2)) == {"e3"}
