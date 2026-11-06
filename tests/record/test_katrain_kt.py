"""Tests for kentogo.record.katrain_kt."""

import base64
import gzip
import json

import pytest

from kentogo.record.katrain_kt import (
    KtEvaluation,
    candidate_losses,
    decode_kt,
    decode_kt_numbers,
    encode_kt,
    evaluate_move,
)


def encode(analysis: dict) -> list[str]:
    """Make the texts of a KT property in the same way as KaTrain (analysis_dumps)."""
    parts = [b"\x00" * 8, b"\x00" * 8, json.dumps(analysis).encode("utf-8")]
    return [base64.standard_b64encode(gzip.compress(part)).decode("utf-8") for part in parts]


ANALYSIS = {
    "root": {"scoreLead": 2.0, "winrate": 0.6, "visits": 500},
    "moves": {
        "Q16": {"scoreLead": 2.5, "order": 0, "visits": 300},
        "D4": {"scoreLead": -1.0, "order": 1, "visits": 100},
        "pass": {"scoreLead": -20.0, "order": 5, "visits": 1},
    },
    "completed": True,
}


def test_decode_kt():
    """The main analysis is read back from KaTrain's texts."""
    assert decode_kt(encode(ANALYSIS)) == ANALYSIS


def test_losses_for_black_and_white():
    """Losses are counted for the player who moves next, from black's scores, and are never below 0."""
    assert candidate_losses(ANALYSIS, "B") == {"Q16": 0.0, "D4": 3.0, "PASS": 22.0}
    assert candidate_losses(ANALYSIS, "W") == {"Q16": 0.5, "D4": 0.0, "PASS": 0.0}


def test_analysis_without_scores():
    """Without a root score or moves, no losses are known."""
    assert candidate_losses({"root": None, "moves": {}}, "B") == {}
    assert candidate_losses({"root": {"scoreLead": 1.0}, "moves": {"Q16": {}}}, "B") == {}


def test_newer_version_and_broken_data():
    """A newer format and broken data are refused."""
    with pytest.raises(ValueError):
        decode_kt(encode(ANALYSIS), version="2.0")
    with pytest.raises(ValueError):
        decode_kt(["AAAA", "AAAA", "not base64 gzip"])
    with pytest.raises(ValueError):
        decode_kt(encode(ANALYSIS)[:2])


AFTER_GOOD = {"root": {"scoreLead": 2.4}}  # Black played almost the best move (Q16).
AFTER_BAD = {"root": {"scoreLead": -5.0}}  # Black lost 7 points.


def test_evaluate_move_loss_best_move_and_sequence():
    """The loss is the score before the move minus the score after it; the best move is ranked first."""
    best = {**ANALYSIS["moves"]["Q16"], "pv": ["Q16", "d4", 5]}
    before = {**ANALYSIS, "moves": {**ANALYSIS["moves"], "Q16": best}}
    assert evaluate_move(before, AFTER_BAD, "B") == KtEvaluation(7.0, "Q16", ("Q16", "D4"))
    assert evaluate_move(before, AFTER_GOOD, "B").points_lost == 0.0


def test_evaluate_move_for_white_and_never_below_zero():
    """For white, black's score going up is a loss; a score that got better counts as 0."""
    assert evaluate_move(ANALYSIS, AFTER_BAD, "W").points_lost == 0.0
    assert evaluate_move(ANALYSIS, {"root": {"scoreLead": 4.5}}, "W").points_lost == 2.5


def test_evaluate_move_without_scores_or_ranks():
    """Without a root score there is no evaluation; without ranked candidates there is no best move."""
    assert evaluate_move({"moves": {}}, AFTER_BAD, "B") is None
    assert evaluate_move(ANALYSIS, {"root": {}}, "B") is None
    unranked = {"root": {"scoreLead": 2.0}, "moves": {"Q16": {"scoreLead": 2.0}}}
    assert evaluate_move(unranked, AFTER_BAD, "B") == KtEvaluation(7.0, None, ())


FULL_ANALYSIS = {
    "moves": {
        "Q16": {
            "move": "Q16",
            "order": 0,
            "scoreLead": 2.5,
            "visits": 300,
            "pv": ["Q16", "D4"],
            "ownership": [0.5] * 4,
        },
        "D4": {"move": "D4", "order": 1, "scoreLead": -1.0, "visits": 100, "pv": ["D4"]},
    },
    "root": {"scoreLead": 2.0, "winrate": 0.6, "visits": 500},
    "ownership": [1.0, -1.0, 0.5, 0.0],
    "policy": [0.25, 0.5, 0.125, 0.0, -1.0],
    "completed": True,
}


def test_encode_kt_reads_back():
    """The main analysis, the ownership and the policy come back (the numbers are 16-bit floats)."""
    texts = encode_kt(FULL_ANALYSIS)
    main = decode_kt(texts)
    assert main["root"] == FULL_ANALYSIS["root"] and main["completed"] is True
    assert "ownership" not in main["moves"]["Q16"]
    assert decode_kt_numbers(texts, 4) == (tuple(FULL_ANALYSIS["ownership"]), tuple(FULL_ANALYSIS["policy"]))
    assert "ownership" in FULL_ANALYSIS["moves"]["Q16"]  # The analysis given is not changed.


def test_encode_kt_without_ownership_or_policy():
    """Without the ownership or the policy, their parts are empty and read back as None."""
    texts = encode_kt({**FULL_ANALYSIS, "ownership": None, "policy": None})
    assert decode_kt_numbers(texts, 4) == (None, None)


def test_decode_kt_numbers_of_broken_data():
    with pytest.raises(ValueError):
        decode_kt_numbers(encode_kt(FULL_ANALYSIS), 9)  # Not the size of the board.
    with pytest.raises(ValueError):
        decode_kt_numbers(["AAAA"], 4)
