"""Tests for kentogo.record.katrain_kt."""

import base64
import gzip
import json

import pytest

from kentogo.record.katrain_kt import candidate_losses, decode_kt


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
