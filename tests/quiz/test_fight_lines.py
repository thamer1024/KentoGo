"""Tests for kentogo.quiz.fight_lines (the sequences shown after a local fight)."""

from kentogo.common.types import Move
from kentogo.quiz.fight_lines import AI_CALCULATING, AI_FAILED, AI_READY, LINE_AI, LINE_GAME, LINE_PLAYED, FightLines

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
    lines.set_ai_line(AI)
    assert (lines.ai_state, points(lines.shown())) == (AI_READY, [(0, 2)])
    lines.next_line()
    assert (lines.name, lines.shown()) == (LINE_GAME, GAME[:1])
    lines.next_line()
    assert (lines.name, lines.shown()) == (LINE_PLAYED, PLAYED[:1])
    lines.previous_line()
    assert lines.name == LINE_GAME
    lines.back()
    lines.back()
    assert lines.shown() == ()


def test_the_sequence_of_the_ais_fails():
    lines = FightLines(PLAYED, GAME)
    lines.ai_failed()
    lines.next_line()
    assert (lines.ai_state, lines.shown(), lines.length) == (AI_FAILED, (), 0)
