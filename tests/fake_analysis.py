"""A fake KataGo engine for the tests of the analyses: it keeps the queries, and the test answers them."""


class FakeEngine:
    """An engine that keeps the queries, so that a test can answer them in any order."""

    def __init__(self):
        """Start with no queries."""
        self.queries: list[tuple[dict, object]] = []

    def query(self, request, callback):
        """Keep the query and its callback."""
        self.queries.append((request, callback))
        return str(len(self.queries))

    def answer(self, index: int, score: float | None = None, error: str | None = None, pv=(), best_score=None) -> None:
        """Answer one query with a score (from black's side) and a sequence, or with an error.

        best_score is the score after the best move (the first move of pv), if given.
        """
        _, callback = self.queries[index]
        if error is not None:
            callback({"id": str(index + 1), "error": error})
        else:
            callback({"id": str(index + 1), "isDuringSearch": True, "rootInfo": {"scoreLead": 99.0}})
            move_infos = [{"move": pv[0], "order": 0, "pv": list(pv)}] if pv else []
            if move_infos and best_score is not None:
                move_infos[0]["scoreLead"] = best_score
            final = {"id": str(index + 1), "isDuringSearch": False, "rootInfo": {"scoreLead": score}}
            callback({**final, "moveInfos": move_infos})

    def answer_standing(self, index: int, lead: float, owner: float, size: int) -> None:
        """Answer a query for the territory: a score lead (from black's side), and the same owner on every point."""
        _, callback = self.queries[index]
        ownership = [owner] * (size * size)
        callback(
            {"id": str(index + 1), "isDuringSearch": False, "rootInfo": {"scoreLead": lead}, "ownership": ownership}
        )
