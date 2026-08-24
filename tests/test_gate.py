"""Promotion gate behaviour.

The gate is the only thing standing between a generated patch and production.
These tests exist to prove it actually blocks, rather than decorating a result
that was going to be 'pass' anyway.
"""
from __future__ import annotations

from apps.api.contracts import ArmMetrics
from apps.api.gate import PairOutcome, evaluate


def metrics(**kw) -> ArmMetrics:
    base = dict(
        double_refund_rate=0.0,
        duplicate_confirmation_rate=0.0,
        premature_escalation_rate=0.0,
        resolution_rate=1.0,
        avg_turns=3.0,
        unsafe_effects=0,
        external_calls_executed=0,
    )
    base.update(kw)
    return ArmMetrics(**base)


def gate(pairs, *, before=1.0, after=0.0, unsafe=0, external=0, prov=True):
    return evaluate(
        target_failure="double_refund",
        baseline_target=metrics(double_refund_rate=before),
        candidate_target=metrics(double_refund_rate=after),
        pairs=pairs,
        candidate_unsafe_effects=unsafe,
        candidate_external_calls=external,
        shadowed_effects=24,
        provenance_ok=prov,
        provenance_detail="captures verified" if prov else "capture is stale",
    )


FIXED = PairOutcome("t1", "target", False, True, ["double_refund"], [])
CLEAN_CONTROL = PairOutcome("c1", "control", True, True, [], [])
BROKEN_CONTROL = PairOutcome("c2", "control", True, False, [], ["premature_escalation"])


def check(result, cid):
    return next(c for c in result.checks if c.id == cid)


def test_clean_candidate_passes_and_is_promotable():
    r = gate([FIXED, CLEAN_CONTROL])
    assert r.verdict == "pass"
    assert r.promotable


def test_control_regression_blocks_promotion():
    r = gate([FIXED, CLEAN_CONTROL, BROKEN_CONTROL])
    assert r.verdict == "fail"
    assert not r.promotable
    c = check(r, "control_preservation")
    assert c.status == "fail"
    assert "c2" in c.evidence, "the gate must name which control broke"


def test_insufficient_target_improvement_blocks():
    r = gate([FIXED, CLEAN_CONTROL], before=1.0, after=0.9)
    assert check(r, "target_improvement").status == "fail"
    assert not r.promotable


def test_unsafe_effect_blocks_even_with_perfect_metrics():
    r = gate([FIXED, CLEAN_CONTROL], unsafe=1)
    assert check(r, "effect_safety").status == "fail"
    assert not r.promotable


def test_executed_external_call_blocks():
    r = gate([FIXED, CLEAN_CONTROL], external=1)
    assert check(r, "effect_safety").status == "fail"
    assert not r.promotable


def test_stale_provenance_blocks_an_otherwise_perfect_candidate():
    """A patch cannot be promoted on evidence that no longer describes it."""
    r = gate([FIXED, CLEAN_CONTROL], prov=False)
    assert check(r, "target_improvement").status == "pass"
    assert check(r, "control_preservation").status == "pass"
    assert check(r, "effect_safety").status == "pass"
    assert check(r, "provenance").status == "fail"
    assert not r.promotable


def test_pending_provenance_is_not_promotable():
    r = evaluate(
        target_failure="double_refund",
        baseline_target=metrics(double_refund_rate=1.0),
        candidate_target=metrics(),
        pairs=[FIXED, CLEAN_CONTROL],
        candidate_unsafe_effects=0,
        candidate_external_calls=0,
        shadowed_effects=0,
        provenance_ok=None,
        provenance_detail="not yet evaluated",
    )
    assert r.verdict == "pending"
    assert not r.promotable
