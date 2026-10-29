"""Tests for kentogo.seichi.arrangement."""

import pytest

from kentogo.common.types import Move, Position
from kentogo.seichi.arrangement import Arrangement, PlacementError, TerritoryChangedError
from kentogo.seichi.territory import TerritoryCount


def position() -> Position:
    """A 9x9 position with a black stone on C3 and E5, and a white stone on G7."""
    moves = (Move.from_gtp("C3", "B"), Move.from_gtp("G7", "W"), Move.from_gtp("E5", "B"))
    return Position(9, 6.5, "japanese", (), moves, "W")


def point(gtp: str) -> tuple[int, int]:
    """Return the point of GTP coordinates."""
    return Move.from_gtp(gtp, "B").coord


def test_start_from_the_final_position():
    """The stones are those of the final position."""
    arrangement = Arrangement(position())
    assert arrangement.stones == {point("C3"): "B", point("G7"): "W", point("E5"): "B"}
    assert not arrangement.can_undo


def test_move_to_an_empty_point():
    """A stone moves to an empty point."""
    arrangement = Arrangement(position())
    assert arrangement.move(point("C3"), point("A1"))
    assert arrangement.stones[point("A1")] == "B" and point("C3") not in arrangement.stones


def test_swap_with_the_other_color():
    """Moving onto a stone of the other color swaps the two stones."""
    arrangement = Arrangement(position())
    assert arrangement.move(point("E5"), point("G7"))
    assert arrangement.stones[point("G7")] == "B" and arrangement.stones[point("E5")] == "W"


def test_moves_that_change_nothing():
    """No stone, the same point, outside the board, or the same color: nothing changes."""
    arrangement = Arrangement(position())
    assert not arrangement.move(point("A9"), point("A1"))
    assert not arrangement.move(point("C3"), point("C3"))
    assert not arrangement.move(point("C3"), (9, 0))
    assert not arrangement.move(point("C3"), point("E5"))
    assert not arrangement.can_undo


def test_undo_and_reset():
    """Changes are taken back one by one, and reset goes back to the final position (and can be undone)."""
    arrangement = Arrangement(position())
    start = arrangement.stones
    arrangement.move(point("C3"), point("A1"))
    moved = arrangement.stones
    arrangement.move(point("E5"), point("G7"))
    assert arrangement.undo() and arrangement.stones == moved
    arrangement.reset()
    assert arrangement.stones == start
    assert arrangement.undo() and arrangement.stones == moved
    assert arrangement.undo() and arrangement.stones == start
    assert not arrangement.undo()


def walls() -> Position:
    """A 5x5 position with a black wall on column B and a white wall on column D (5 points each)."""
    moves = []
    for row in range(1, 6):
        moves += [Move.from_gtp(f"B{row}", "B"), Move.from_gtp(f"D{row}", "W")]
    return Position(5, 6.5, "japanese", (), tuple(moves), "B")


def test_move_that_changes_the_territory_is_refused():
    """Opening a hole in a wall changes the territory, so the move is refused and nothing changes."""
    arrangement = Arrangement(walls())
    start = arrangement.stones
    assert arrangement.territory == TerritoryCount(5, 5)
    with pytest.raises(TerritoryChangedError) as refused:
        arrangement.move(point("B3"), point("C3"))
    assert refused.value.before == TerritoryCount(5, 5)
    assert refused.value.after == TerritoryCount(6, 5)  # B3 joins black's area.
    assert arrangement.stones == start and not arrangement.can_undo


def test_move_inside_own_territory_is_made():
    """Moving a stone from one point of its own territory to another keeps the count, so it is made."""
    moves = [Move.from_gtp(f"C{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A1", "B")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "W"))
    assert arrangement.territory == TerritoryCount(19, 0)  # Columns A, B (but A1), D and E.
    assert arrangement.move(point("A1"), point("B5"))
    assert arrangement.territory == TerritoryCount(19, 0) and arrangement.can_undo


def test_dead_group_is_marked_and_counted_as_not_on_the_board():
    """Clicking a stone marks its whole group dead. The area around it then becomes the surrounder's territory."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)]
    moves += [Move.from_gtp("A2", "W"), Move.from_gtp("A3", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    assert arrangement.territory == TerritoryCount(15, 0)  # Columns C to E. Column A touches white.
    assert arrangement.toggle_dead(point("A2"))
    assert arrangement.dead == {point("A2"), point("A3")}  # The whole group.
    assert arrangement.territory == TerritoryCount(20, 0)  # Column A is black's too.
    assert arrangement.toggle_dead(point("A3"))  # Clicking again makes the group alive.
    assert arrangement.dead == frozenset() and arrangement.territory == TerritoryCount(15, 0)
    assert not arrangement.toggle_dead(point("E5"))  # No stone there.


def test_dead_mark_moves_with_its_stone_and_can_be_undone():
    """A dead stone keeps its mark when moved, and marking is taken back with undo."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement.toggle_dead(point("A2"))
    assert arrangement.move(point("A2"), point("A5"))  # Moving a dead stone inside the territory keeps it.
    assert arrangement.dead == {point("A5")}
    assert arrangement.undo() and arrangement.dead == {point("A2")}
    assert arrangement.undo() and arrangement.dead == frozenset()
    arrangement.toggle_dead(point("A2"))
    arrangement.reset()
    assert arrangement.dead == frozenset()


def captured_position() -> Position:
    """A 5x5 position: black captured a white stone on A1, and has a wall on column C (white is on E)."""
    moves = [
        Move.from_gtp("B1", "B"),
        Move.from_gtp("A1", "W"),
        Move.from_gtp("A2", "B"),  # Captures A1.
    ]
    moves += [Move.from_gtp(f"C{row}", "B") for row in range(1, 6)]
    moves += [Move.from_gtp(f"D{row}", "W") for row in range(1, 6)]
    return Position(5, 6.5, "japanese", (), tuple(moves), "W")


def test_prisoners_come_from_the_captures():
    """The stones captured during the game are in the trays: here one white stone held by black."""
    arrangement = Arrangement(captured_position())
    assert arrangement.prisoners == {"B": 0, "W": 1}


def test_remove_dead_puts_them_in_the_trays():
    """Dead stones go to the tray of their color, and the territory stays the same."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement.toggle_dead(point("A2"))
    territory = arrangement.territory
    assert arrangement.remove_dead() == 1
    assert arrangement.prisoners == {"B": 0, "W": 1}
    assert point("A2") not in arrangement.stones and arrangement.territory == territory
    assert arrangement.undo() and arrangement.dead == {point("A2")}
    assert arrangement.remove_dead() == 1 and arrangement.remove_dead() == 0


def test_prisoner_goes_only_into_its_own_colors_territory():
    """A white prisoner fills white's territory (one point less). Black's territory or dame is refused."""
    arrangement = Arrangement(captured_position())
    white_territory = arrangement.territory.white
    with pytest.raises(PlacementError, match="prisoner_not_own_territory"):
        arrangement.place_prisoners("W", point("B3"))  # Black's territory.
    with pytest.raises(PlacementError, match="prisoner_none"):
        arrangement.place_prisoners("B", point("E3"))  # No black prisoners.
    arrangement.place_prisoners("W", point("E3"))
    assert arrangement.territory.white == white_territory - 1
    assert arrangement.prisoners == {"B": 0, "W": 0} and arrangement.placed == {point("E3")}


def test_prisoner_can_be_taken_back():
    """A prisoner put on the board goes back to its tray. Other stones cannot."""
    arrangement = Arrangement(captured_position())
    arrangement.place_prisoners("W", point("E3"))
    assert not arrangement.take_back_prisoner(point("D3"))
    assert arrangement.take_back_prisoner(point("E3"))
    assert arrangement.prisoners == {"B": 0, "W": 1} and point("E3") not in arrangement.stones


def test_many_prisoners_fill_the_area_from_the_edge():
    """Several prisoners fill the area where they are dropped, from the points nearest the board edge."""
    moves = [Move.from_gtp(f"C{row}", "B") for row in range(1, 6)] + [
        Move.from_gtp(f"D{row}", "W") for row in range(1, 6)
    ]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement._state = arrangement._state.with_prisoners({"B": 12, "W": 0})  # Black stones that white holds.
    assert arrangement.place_prisoners("B", point("B3"), 3) == 3
    placed = arrangement.placed
    assert all(x == 0 or y in (0, 4) for x, y in placed)  # On the edge of the board.
    assert point("A3") in placed  # Nearest to where they were dropped, on the edge.
    assert arrangement.prisoners["B"] == 9
    # More than the area has: only as many as fit (10 points, 3 used), and the rest stay in the tray.
    assert arrangement.place_prisoners("B", point("B3"), 10) == 7
    assert arrangement.prisoners["B"] == 2 and arrangement.territory.black == 0
    assert arrangement.undo() and arrangement.prisoners["B"] == 9  # One undo takes back the whole drop.


def test_fill_dame():
    """Clicking an open dame fills it with a stone (black when safe). Clicking a territory point is refused."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in (1, 2, 4, 5)] + [
        Move.from_gtp(f"D{row}", "W") for row in range(1, 6)
    ]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    assert point("B3") in arrangement.open_dame and not arrangement.ready_for_auto
    assert arrangement.fill_dame(point("B3")) == "B"
    assert arrangement.filled_dame == {point("B3")} and arrangement.territory.black == 5
    with pytest.raises(PlacementError, match="dame_not_dame"):
        arrangement.fill_dame(point("A3"))  # Black's territory now.
    assert not arrangement.move(point("B3"), point("A3"))  # A dame stone does not move.
    assert arrangement.remove_dame(point("B3")) and point("B3") in arrangement.open_dame
    assert not arrangement.remove_dame(point("B1"))  # Not a dame stone.


def test_a_liberty_that_cannot_be_filled_is_left_as_seki():
    """A1 between black B1 and white A2 cannot be filled (either stone would be in atari).

    goscorer sees the groups as seki, so A1 is neutral: it is not a dame to fill, and not territory.
    """
    moves = (Move.from_gtp("B1", "B"), Move.from_gtp("A2", "W"), Move.from_gtp("B2", "W"), Move.from_gtp("C1", "W"))
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), moves, "B"))
    assert point("A1") in arrangement.neutral and point("A1") not in arrangement.open_dame
    with pytest.raises(PlacementError, match="dame_not_dame"):
        arrangement.fill_dame(point("A1"))
    assert point("A1") not in arrangement.stones and not arrangement.can_undo


def test_take_off_one_dead_stone():
    """A dead stone dragged off the board goes to the tray of its color. A live stone does not."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    assert not arrangement.take_off_dead(point("A2"))
    arrangement.toggle_dead(point("A2"))
    assert arrangement.take_off_dead(point("A2"))
    assert arrangement.prisoners == {"B": 0, "W": 1} and arrangement.dead == frozenset()


def test_auto_fill_needs_the_users_part_first():
    """auto_fill works only after the dead stones are off and the dame are filled. One undo takes it back."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement.toggle_dead(point("A2"))
    with pytest.raises(PlacementError, match="auto_not_ready"):
        arrangement.auto_fill()
    arrangement.remove_dead()
    assert arrangement.ready_for_auto
    result = arrangement.auto_fill()
    # The white prisoner has no white territory to go to: it is left over.
    assert result.left == {"B": 0, "W": 1}
    assert result.areas == {"B": [20], "W": []}  # The black wall between them is moved: one area of 20.
    assert arrangement.undo() and arrangement.territory.black == 20  # One undo: back to before auto_fill.
    assert arrangement.stones[point("B3")] == "B"


def test_auto_fill_captures_groups_without_liberties():
    """A group with no liberty is taken off as prisoners first, and filled into its own color's territory.

    Such a group can be left by the user's moves; here it is given as setup stones.
    """
    black = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A3", "B")]
    white = [Move.from_gtp("A1", "W"), Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", tuple(black + white), (), "B"))
    assert arrangement.ready_for_auto
    result = arrangement.auto_fill()
    assert result.captured == {"B": 0, "W": 2}
    # The 2 points where the captured stones were become black territory. The white prisoners
    # would fill white territory, but white has none, so they are left over (and counted for black).
    # The 2 + 2 points on the A line become one rectangle of 4 (the stone on A3 moves to an end of it).
    assert result.areas == {"B": [15, 4], "W": []} and result.left == {"B": 0, "W": 2}
    assert "W" not in arrangement.stones.values()


def test_auto_fill_keeps_its_steps_and_is_done_once():
    """The steps end with the stones now; auto_fill cannot be done again until it is taken back."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement.toggle_dead(point("A2"))
    arrangement.remove_dead()
    arrangement._state = arrangement._state.with_prisoners({"B": 3, "W": 1})
    start = arrangement.stones
    result = arrangement.auto_fill()
    assert result.start == start and result.steps
    assert result.steps[-1].stones == arrangement.stones
    assert not arrangement.ready_for_auto and arrangement.auto_done
    with pytest.raises(PlacementError, match="auto_not_ready"):
        arrangement.auto_fill()
    arrangement.undo()
    assert arrangement.ready_for_auto and not arrangement.auto_done


def test_auto_fill_does_not_capture_filled_territory():
    """A group the user filled with prisoners has no liberty, but it is not captured."""
    black = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)]
    arrangement = Arrangement(Position(5, 6.5, "japanese", tuple(black), (), "B"))
    arrangement._state = arrangement._state.with_prisoners({"B": 5, "W": 0})
    assert arrangement.place_prisoners("B", point("A1"), 5) == 5  # Column A is full now.
    result = arrangement.auto_fill()
    assert result.captured == {"B": 0, "W": 0}


def test_auto_fill_puts_the_prisoners_first():
    """The prisoners go into the territory first; the stones move after them."""
    black = [Move.from_gtp(f"C{row}", "B") for row in range(1, 6)]
    white = [Move.from_gtp(f"D{row}", "W") for row in range(1, 6)]
    arrangement = Arrangement(Position(5, 6.5, "japanese", tuple(black + white), (), "B"))
    arrangement._state = arrangement._state.with_prisoners({"B": 3, "W": 0})
    result = arrangement.auto_fill()
    kinds = [step.kind for step in result.steps]
    assert kinds[:3] == ["place"] * 3 and "place" not in kinds[3:]
    assert result.steps[-1].stones == arrangement.stones and arrangement.prisoners == {"B": 0, "W": 0}


def test_seki_eyes_are_not_territory_and_stay_empty():
    """In a seki, the eyes are not counted, need no filling, and the computer's seichi leaves them empty."""
    stones = []
    for y in range(1, 10):
        if y != 5:
            stones += [
                Move.from_gtp(f"A{y}", "B"),
                Move.from_gtp(f"E{y}", "W"),
                Move.from_gtp(f"C{y}", "B" if y < 5 else "W"),
            ]
        stones += [Move.from_gtp(f"B{y}", "B"), Move.from_gtp(f"D{y}", "W"), Move.from_gtp(f"F{y}", "W")]
        stones += [Move.from_gtp(f"G{y}", "B")]
    arrangement = Arrangement(Position(9, 6.5, "japanese", tuple(stones), (), "B"))
    assert (arrangement.territory.black, arrangement.territory.white) == (18, 0)
    assert arrangement.ready_for_auto
    arrangement.auto_fill()
    assert {point("A5"), point("C5"), point("E5")}.isdisjoint(arrangement.stones)
    assert (arrangement.territory.black, arrangement.territory.white) == (18, 0)


def test_a_plan_is_not_used_after_the_stones_changed():
    """The computer's seichi is planned on the stones of one moment; after a change it is not used."""
    black = [Move.from_gtp(f"C{row}", "B") for row in range(1, 6)]
    white = [Move.from_gtp(f"D{row}", "W") for row in range(1, 6)]
    arrangement = Arrangement(Position(5, 6.5, "japanese", tuple(black + white), (), "B"))
    plan = arrangement.plan_auto()
    assert not arrangement.auto_done  # Planning does not change the stones.
    arrangement.move(point("C1"), point("C1"))  # Nothing changes: the plan is still good.
    assert arrangement.use_auto(plan) and arrangement.auto_done
    arrangement.undo()
    arrangement.toggle_dead(point("C1"))  # Any change makes the plan old, even one taken back.
    arrangement.toggle_dead(point("C1"))
    assert not arrangement.use_auto(plan)


def test_auto_fill_moves_stones_and_keeps_the_territory():
    """Stones only move (no stone changes color), the white wall stays, and the territory stays the same."""
    black = [Move.from_gtp(f"C{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A3", "B")]
    white = [Move.from_gtp(f"D{row}", "W") for row in range(1, 6)]
    arrangement = Arrangement(Position(5, 6.5, "japanese", tuple(black + white), (), "B"))
    result = arrangement.auto_fill()
    assert {step.kind for step in result.steps} <= {"place", "move"}
    colors = list(arrangement.stones.values())
    assert colors.count("B") == 6 and colors.count("W") == 5
    assert all(arrangement.stones.get(point(f"D{row}")) == "W" for row in range(1, 6))
    assert arrangement.territory == TerritoryCount(9, 5)
    assert result.areas == {"B": [5, 4], "W": [5]}


def two_walls() -> Arrangement:
    """A 5 x 5 board: black wall on column B, white wall on column C. A is black's (5), D and E white's (10)."""
    stones = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [
        Move.from_gtp(f"C{row}", "W") for row in range(1, 6)
    ]
    return Arrangement(Position(5, 6.5, "japanese", tuple(stones), (), "B"))


def test_after_confirming_any_move_is_allowed_and_the_territory_is_remembered():
    """Before confirming, a move that changes the territory is refused; after it, the boundary may move."""
    arrangement = two_walls()
    with pytest.raises(TerritoryChangedError):
        arrangement.move(point("B3"), point("A3"))
    with pytest.raises(PlacementError, match="mark_not_seichi"):
        arrangement.mark_area(point("A1"))
    assert arrangement.ready_to_confirm and not arrangement.in_seichi
    arrangement.confirm()
    assert arrangement.in_seichi and arrangement.confirmed_count == TerritoryCount(5, 10)
    assert arrangement.move(point("B3"), point("A3"))  # The black wall is open now: A touches white.
    # The points of A keep their owner from the confirmed end; B3 (a stone then) is nobody's yet.
    assert arrangement.territory == TerritoryCount(4, 10)
    assert arrangement.undecided == {point("B3")}
    assert not arrangement.toggle_dead(point("A3"))  # Dead marks are not changed any more.


def test_the_user_sets_who_owns_an_empty_point():
    """A click on an empty point sets its owner: black, white, nobody, in turn (the area with it)."""
    arrangement = two_walls()
    arrangement.confirm()
    arrangement.move(point("B3"), point("A3"))
    assert arrangement.mark_area(point("B3")) == "B"
    assert arrangement.territory == TerritoryCount(5, 10) and not arrangement.undecided
    assert arrangement.mark_area(point("B3")) == "W"
    assert arrangement.territory == TerritoryCount(4, 11)
    assert arrangement.mark_area(point("B3")) == ""
    assert arrangement.territory == TerritoryCount(4, 10) and not arrangement.undecided
    with pytest.raises(PlacementError, match="mark_not_empty"):
        arrangement.mark_area(point("A3"))
    arrangement.undo()
    arrangement.undo()
    assert arrangement.territory_points[point("B3")] == "B"


def test_the_computers_seichi_starts_from_the_confirmed_end():
    """Moves made after confirming are not used by the computer; the end stays confirmed."""
    arrangement = two_walls()
    arrangement.confirm()
    arrangement.move(point("B3"), point("A3"))
    result = arrangement.auto_fill()
    assert result.start == two_walls().stones
    assert arrangement.in_seichi and arrangement.territory == TerritoryCount(5, 10)


def test_a_point_not_counted_by_goscorer_can_be_set_by_the_user():
    """A point of seki (or a false eye) is nobody's at first, but the user can make it territory."""
    arrangement = Arrangement(
        Position(
            5,
            6.5,
            "japanese",
            (),
            tuple(
                [Move.from_gtp("B1", "B"), Move.from_gtp("A2", "W"), Move.from_gtp("B2", "W"), Move.from_gtp("C1", "W")]
            ),
            "B",
        )
    )
    assert point("A1") in arrangement.neutral
    arrangement.confirm()
    assert arrangement.mark_area(point("A1")) == "B"
    assert arrangement.territory_points[point("A1")] == "B"


def test_the_margin_stays_the_same_through_the_seichi():
    """The lead (territory and prisoners held) counts dead-marked stones, and the computer's seichi keeps it."""
    stones = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [
        Move.from_gtp(f"C{row}", "W") for row in range(1, 6)
    ]
    stones.append(Move.from_gtp("E3", "B"))  # A dead black stone in white's territory.
    arrangement = Arrangement(Position(5, 6.5, "japanese", tuple(stones), (), "B"))
    arrangement._state = arrangement._state.with_prisoners({"B": 2, "W": 3})
    arrangement.toggle_dead(point("E3"))
    assert arrangement.pending_prisoners == {"B": 1, "W": 0}
    before = arrangement.margin  # Black: 5 + 3 white prisoners; white: 10 + 2 + 1 black prisoners.
    assert before == 8 - 13
    arrangement.remove_dead()
    assert arrangement.margin == before and arrangement.prisoners == {"B": 3, "W": 3}
    arrangement.auto_fill()
    assert arrangement.margin == before


def test_auto_fill_keeps_the_prisoners_before_it():
    """The prisoners before the computer's seichi are kept, so that the trays can be shown at each step."""
    moves = [Move.from_gtp(f"B{row}", "B") for row in range(1, 6)] + [Move.from_gtp("A2", "W")]
    arrangement = Arrangement(Position(5, 6.5, "japanese", (), tuple(moves), "B"))
    arrangement.toggle_dead(point("A2"))
    arrangement.remove_dead()
    arrangement._state = arrangement._state.with_prisoners({"B": 3, "W": 1})
    before = dict(arrangement.prisoners)
    result = arrangement.auto_fill()
    assert result.start_prisoners == before and before == {"B": 3, "W": 1}
    assert result.steps[-1].prisoners == arrangement.prisoners


def test_check_count_after_the_users_seichi():
    """The seichi is checked against the confirmed territory less the prisoners."""
    arrangement = two_walls()
    with pytest.raises(PlacementError, match="count_not_seichi"):
        arrangement.check_count()
    arrangement.confirm()
    check = arrangement.check_count()
    assert check.right == check.board == TerritoryCount(5, 10) and check.passed
    arrangement.move(point("B3"), point("C3"))  # Swapped: each wall has one stone of the other color.
    mixed = arrangement.check_count()
    assert mixed.board == TerritoryCount(5, 10) and mixed.passed  # Most of the stones around still tell.


def test_check_count_takes_the_prisoners_left_off_the_territory():
    """Prisoners still in a tray are taken off their color's territory, as if they had been put."""
    arrangement = two_walls()
    arrangement._state = arrangement._state.with_prisoners({"B": 0, "W": 2})
    arrangement.confirm()
    check = arrangement.check_count()
    assert check.right == TerritoryCount(5, 8) and check.prisoners_left == {"B": 0, "W": 2}
    assert check.board == TerritoryCount(5, 10) and check.counted == check.right and check.passed
