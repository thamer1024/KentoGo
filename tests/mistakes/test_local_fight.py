"""Tests for kentogo.mistakes.local_fight, and the local fights of mistakes.extract."""

from test_extract import extract, game

from kentogo.common.types import Move
from kentogo.mistakes.local_fight import local_fight_id
from kentogo.mistakes.problem import problem_id_of
from kentogo.quiz.problem_json import local_fight_from_dict, local_fight_to_dict, result_from_dict, result_to_dict
from kentogo.record.kentogo_analysis import KGA_PROPERTY, KIND_BOUNDARY, KIND_LIFE_DEATH, encode_kga


def with_fight(text: str, node: str, moves: int, kind: str = KIND_LIFE_DEATH) -> str:
    """Put a local fight into KGA of the node (such as ";W[dp]"), with black's score lead 1.5."""
    fight = {"kind": kind, "mine": ["A19", "B19", "C19"], "theirs": [], "points": ["A18"], "moves": moves}
    data = {"root": {"scoreLead": 1.5}, "moves": {}, "local_fight": fight}
    kga = KGA_PROPERTY + "".join(f"[{value}]" for value in encode_kga(data))
    return text.replace(f"{node}C[", f"{node}{kga}C[", 1)


def test_a_local_fight_is_made_from_where_it_starts():
    """The fight starts after white's move 2: black plays move 3; the game's moves follow."""
    result = extract(with_fight(game(), ";W[dp]", 1))
    (fight,) = result.local_fights
    assert (fight.move_number, fight.lost_move_number, fight.moves) == (3, 3, 1)
    assert fight.position.moves == (Move("B", (15, 15)), Move("W", (3, 3))) and fight.position.next_color == "B"
    assert (fight.kind, fight.mine, fight.points, fight.score_lead) == (
        KIND_LIFE_DEATH,
        ("A19", "B19", "C19"),
        ("A18",),
        1.5,
    )
    assert len(fight.game_line) == 5 and fight.game_line[0] == Move("B", (0, 18))  # The fight's move and 4 more.
    assert fight.problem_id == local_fight_id(fight.position) != problem_id_of(fight.position)
    assert fight.mistake_ids() == {problem_id_of(fight.position)}  # The mistake problem of black's move 3.


def test_the_users_moves_inside_a_fight_are_no_mistake_problems():
    """A fight of 1 move takes black's move 3 out of the mistake problems; a fight of 3 moves takes 3 and 5."""
    assert [p.move_number for p in extract(game()).problems] == [7, 3]
    assert [p.move_number for p in extract(with_fight(game(), ";W[dp]", 1)).problems] == [7]
    assert [p.move_number for p in extract(with_fight(game(), ";W[dp]", 3), min_points_lost=1.0).problems] == [7]


def test_a_fight_where_the_opponent_is_to_play_is_not_used():
    """A fight kept after black's own move is not the user's (white would be to play), and broken data is skipped."""
    assert extract(with_fight(game(), ";B[aa]", 1)).local_fights == ()
    assert extract(with_fight(game(), ";W[dp]", 0)).local_fights == ()  # No move of the fight.
    assert extract(with_fight(game(), ";W[dp]", 1, kind="other")).local_fights == ()


def test_local_fights_are_kept_in_the_cache_form():
    """A fight goes into the problem cache's dict and comes back the same."""
    result = extract(with_fight(game(), ";W[dd]", 3, kind=KIND_BOUNDARY))
    (fight,) = result.local_fights
    assert fight.kind == KIND_BOUNDARY and fight.move_number == 5
    assert local_fight_from_dict(local_fight_to_dict(fight)) == fight
    assert result_from_dict(result_to_dict(result)) == result
