"""Tests for kentogo.quiz.fight_lines (the sequences shown after a local fight)."""

from kentogo.common.types import Move
from kentogo.quiz.fight_follow import END_LEFT, FollowEnd
from kentogo.quiz.fight_lines import (
    AI_CALCULATING,
    AI_FAILED,
    AI_READY,
    LINE_AI,
    LINE_GAME,
    LINE_PLAYED,
    LINE_STRONG,
    FightLines,
)

END = FollowEnd(END_LEFT)
PLAYED = (Move("B", (0, 1)), Move("W", (1, 1)), Move("B", (2, 1)))
GAME = (Move("B", (3, 3)), Move("W", (4, 3)))
AI = (Move("B", (0, 2)), Move("W", (1, 2)))


def points(moves) -> list:
    return [move.coord for move in moves]


def test_the_moves_played_are_shown_first_to_their_end():
    lines = FightLines(PLAYED, GAME)
    assert (lines.name, lines.shown(), lines.ai_state) == (LINE_PLAYED, PLAYED, AI_CALCULATING)
    lines.forward()
    assert lines.step == 3  # Not after the last move.
    lines.back()
    assert lines.shown() == PLAYED[:2]


def test_tab_goes_through_the_sequences_from_their_first_moves():
    lines = FightLines(PLAYED, GAME)
    lines.next_line()
    assert (lines.name, lines.shown()) == (LINE_AI, ())  # Still coming.
    lines.set_ai_line(AI, END)
    assert (lines.ai_state, points(lines.shown()), lines.ai_end) == (AI_READY, [(0, 2)], END)
    lines.next_line()
    assert (lines.name, lines.shown()) == (LINE_GAME, GAME[:1])
    lines.next_line()
    assert (lines.name, lines.shown()) == (LINE_PLAYED, PLAYED[:1])
    lines.previous_line()
    assert lines.name == LINE_GAME
    lines.back()
    lines.back()
    assert lines.shown() == ()


def test_the_sequence_of_the_ais_grows_while_it_is_made():
    lines = FightLines(PLAYED, GAME)
    lines.show_ai_line()
    assert (lines.name, lines.shown()) == (LINE_AI, ())
    lines.update_ai_line(AI[:1])
    assert (lines.ai_state, points(lines.shown())) == (AI_CALCULATING, [(0, 2)])  # The first move is shown at once.
    lines.update_ai_line(AI)
    lines.forward()
    assert (lines.ai_state, lines.step, lines.length) == (AI_CALCULATING, 2, 2)
    lines.set_ai_line(AI, END)
    assert lines.ai_state == AI_READY


def test_the_strongest_ai_is_shown_from_its_first_move_as_it_comes():
    lines = FightLines(PLAYED, GAME)
    assert not lines.strong_asked
    lines.start_strong_line()
    assert (lines.strong_asked, lines.count, lines.name, lines.shown()) == (True, 4, LINE_STRONG, ())
    assert lines.strong_state == AI_CALCULATING
    lines.update_strong_line(AI[:1])
    assert (lines.strong_state, points(lines.shown())) == (AI_CALCULATING, [(0, 2)])  # The first move at once.
    lines.set_strong_line(AI, END)
    assert (lines.strong_state, lines.strong_end, lines.length) == (AI_READY, END, 2)


def test_the_strongest_ai_can_be_shown_again_from_its_first_move():
    lines = FightLines(PLAYED, GAME)
    lines.show_strong_line()  # Not started: nothing happens.
    assert lines.name == LINE_PLAYED
    lines.start_strong_line()
    lines.set_strong_line(AI, END)
    lines.show_ai_line()
    lines.forward()
    lines.show_strong_line()
    assert (lines.name, lines.step, points(lines.shown())) == (LINE_STRONG, 1, [(0, 2)])


def test_tab_goes_through_the_sequence_of_the_strongest_ai():
    lines = FightLines(PLAYED, GAME)
    lines.start_strong_line()
    lines.next_line()
    assert lines.name == LINE_PLAYED  # After the last, the first.
    lines.previous_line()
    assert lines.name == LINE_STRONG


def test_the_sequence_of_the_strongest_ai_fails():
    lines = FightLines(PLAYED, GAME)
    lines.start_strong_line()
    lines.strong_failed()
    assert (lines.strong_state, lines.length) == (AI_FAILED, 0)


def test_the_sequence_of_the_ais_fails():
    lines = FightLines(PLAYED, GAME)
    lines.ai_failed()
    lines.next_line()
    assert (lines.ai_state, lines.shown(), lines.length) == (AI_FAILED, (), 0)
