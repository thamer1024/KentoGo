"""Games and answers shared by the tests of the AI commentary (imported by the test modules)."""

import json

from kentogo.record.katrain_comment import INTERNAL_MARKER

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"


def katrain(number: int, color: str, point: str, loss: float, best: str) -> str:
    """Make KaTrain's English comment for a move."""
    return (
        f"\nMove {number}: {color} {point}\nEstimated point loss: {loss:.1f}\n"
        f"Predicted top move was {best} (B+1.0).\nPV: {color}{best}\n{INTERNAL_MARKER}"
    )


def analyzed_game(black: str = HUMAN, white: str = AI, komi: float = 6.5, extra: str = "") -> str:
    """A 9x9 game that KaTrain has analyzed: black loses points with moves 1 and 3."""
    return (
        f"(;GM[1]FF[4]CA[UTF-8]SZ[9]KM[{komi}]PB[{black}]PW[{white}]{extra}"
        f";B[ee]C[{katrain(1, 'B', 'E5', 4.0, 'C3')}]"
        ";W[cg]"
        f";B[gc]C[{katrain(3, 'B', 'G7', 6.0, 'D4')}]"
        ";W[df])"
    )


NOT_ANALYZED = f"(;GM[1]FF[4]SZ[9]KM[6.5]PB[{HUMAN}]PW[{AI}];B[ee];W[cg])"

FIELDS = {"situation": "戦い", "category": "misread", "what_happened": "a", "aim": "b", "lesson": "c"}
SUMMARY = {"category_counts": "読み違い 2", "main_issue": "x", "next_focus": "y", "loss_comparison": "z"}


def good_answer(moves=(1, 3)) -> str:
    """An answer for the moves, as a chat screen gives it."""
    data = {"moves": [{"move": move, **FIELDS} for move in moves], "summary": SUMMARY}
    return "```json\n" + json.dumps(data, ensure_ascii=False) + "\n```"
