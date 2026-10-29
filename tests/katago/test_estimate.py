"""Tests for kentogo.katago.estimate and the ownership helpers of katago.queries."""

from kentogo.common.types import Move, Position
from kentogo.katago.estimate import estimate_standing, played
from kentogo.katago.evaluate import EvaluationSettings
from kentogo.katago.queries import ownership_map, with_ownership

SIZE = 3
POSITION = Position(SIZE, 6.5, "japanese", (), (Move.from_gtp("B2", "B"),), "W")


class FakeEngine:
    """An engine that keeps the queries, so that a test can answer them."""

    def __init__(self):
        """Start with no queries."""
        self.queries = []

    def query(self, request, callback):
        """Keep the query and its callback."""
        self.queries.append((request, callback))
        return str(len(self.queries))


def answer(lead: float, owner: float) -> dict:
    """A final answer with a score lead and the same owner on every point."""
    return {"isDuringSearch": False, "rootInfo": {"scoreLead": lead}, "ownership": [owner] * (SIZE * SIZE)}


def test_ownership_map_reads_rows_from_the_top():
    """KataGo's first value is the top left point (A3 on a 3 x 3 board), the last the bottom right (C1)."""
    values = [0.0] * 9
    values[0], values[8] = 1.0, -1.0
    owners = ownership_map({"ownership": values}, SIZE)
    assert owners[(0, 2)] == 1.0 and owners[(2, 0)] == -1.0
    assert with_ownership({"id": "1"}) == {"id": "1", "includeOwnership": True}


def test_played_adds_moves_and_changes_the_player():
    """After white's move, black is to play."""
    after = played(POSITION, (Move.from_gtp("A1", "W"),))
    assert after.moves[-1] == Move.from_gtp("A1", "W") and after.next_color == "B"
    assert played(POSITION, ()) is POSITION


def test_the_standing_of_a_sequence_and_the_game():
    """The end of the sequence and the game are both analyzed; the gain is for the player of the first move."""
    engine, done, errors = FakeEngine(), [], []
    game = played(POSITION, (Move.from_gtp("C3", "W"),))
    end = played(POSITION, (Move.from_gtp("A1", "W"),))
    estimate_standing(engine, end, game, "W", EvaluationSettings(estimate_visits=30), done.append, errors.append)
    assert [request["includeOwnership"] for request, _ in engine.queries] == [True, True]
    assert [request["maxVisits"] for request, _ in engine.queries] == [30, 30]
    engine.queries[1][1](answer(2.0, 0.5))  # The game: black leads by 2.
    engine.queries[0][1](answer(-1.0, -0.5))  # The end of the sequence: white leads by 1.
    standing = done[0]
    assert (standing.end.lead, standing.game.lead, standing.gain) == (-1.0, 2.0, 3.0) and errors == []
