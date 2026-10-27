"""
Tests for FactCheckOracle.

Part 1 tests the pure consensus rules (aggregate / normalize / equivalent).
They need no network. To run them outside GenLayer, copy the helper functions
into a module (or run inside the GenLayer test environment).

Part 2 is an integration sketch for gltest (GenLayer Studio).
"""
import pytest
from fact_check_oracle import aggregate, normalize, equivalent, TRUE, FALSE, UNCLEAR

S, R, N = "SUPPORTS", "REFUTES", "NEUTRAL"


# ---------- Part 1: pure logic ----------
def test_all_support_is_true():
    assert aggregate([S, S, S], 2) == TRUE


def test_all_refute_is_false():
    assert aggregate([R, R, N], 2) == FALSE


def test_split_is_unclear():
    assert aggregate([S, R], 2) == UNCLEAR


def test_not_enough_evidence_is_unclear():
    assert aggregate([S, N, N], 2) == UNCLEAR


def test_normalize_garbage_is_safe():
    out = normalize("not json at all", 3)
    assert out == {"stances": [N, N, N], "confidence": 0}


def test_normalize_buckets_confidence_and_fixes_bad_stance():
    raw = {"sources": [{"stance": "supports"}, {"stance": "maybe"}], "confidence": 87}
    out = normalize(raw, 3)
    assert out["stances"] == [S, N, N]
    assert out["confidence"] == 90


def test_equivalent_accepts_small_noise():
    a = {"stances": [S, S, R], "confidence": 80}
    b = {"stances": [S, S, N], "confidence": 70}
    assert equivalent(a, b, 2)


def test_equivalent_rejects_verdict_flip():
    a = {"stances": [S, S, S], "confidence": 80}
    b = {"stances": [R, R, S], "confidence": 80}
    assert not equivalent(a, b, 2)


def test_equivalent_rejects_big_confidence_gap():
    a = {"stances": [S, S], "confidence": 90}
    b = {"stances": [S, S], "confidence": 40}
    assert not equivalent(a, b, 2)


def test_equivalent_rejects_lying_leader():
    # leader stances say FALSE; validator sees TRUE
    a = {"stances": [R, R, R], "confidence": 80}
    b = {"stances": [S, S, S], "confidence": 80}
    assert not equivalent(a, b, 2)


# ---------- Part 2: integration sketch (gltest) ----------
# from gltest import get_contract_factory
#
# def test_check_claim_settles():
#     factory = get_contract_factory("FactCheckOracle")
#     oracle = factory.deploy(args=[])
#     oracle.check_claim(
#         args=["The Earth orbits the Sun",
#               ["https://en.wikipedia.org/wiki/Earth",
#                "https://www.nasa.gov/earth/"], 2]
#     ).transact()
#     assert oracle.get_verdict(args=[0]).call() == "TRUE"
