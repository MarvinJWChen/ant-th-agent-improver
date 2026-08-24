"""Cached startup and capture provenance.

Two claims are protected here. First, the default demo path needs no API key.
Second — and this is the one that matters — a capture that no longer matches the
execution it is standing in for cannot authorise a promotion. Without that,
cached mode would just be a way to ship a patch on evidence about a different
program.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api import store
from apps.api.llm import capture as cap
from apps.api.llm import runner
from apps.api.main import app

pytestmark = pytest.mark.skipif(not store.corpus_available(), reason="corpus not seeded")


def key(**over) -> cap.ProvenanceKey:
    base = dict(
        task="test_task",
        task_version="1.0",
        model="claude-opus-5",
        prompt_hash="p" * 8,
        inputs_hash="i" * 8,
        output_schema_hash="o" * 8,
        agent_config_hash="a" * 8,
        tools_hash="t" * 8,
        corpus_hash="c" * 8,
        world_hash="w" * 8,
        loop_version="L1",
    )
    base.update(over)
    return cap.ProvenanceKey(**base)


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(cap.paths, "CAPTURES", tmp_path)
    k = key()
    cap.save(k, {"answer": 42})
    return k


def test_exact_match_verifies(saved):
    found, verified, reason, mismatches = cap.resolve(saved)
    assert found is not None and verified
    assert not mismatches
    assert "verified" in reason.lower()


@pytest.mark.parametrize(
    "field",
    ["task_version", "model", "prompt_hash", "inputs_hash", "output_schema_hash",
     "agent_config_hash", "tools_hash", "corpus_hash", "world_hash", "loop_version"],
)
def test_every_provenance_field_invalidates_a_capture(saved, field):
    """Each field is load-bearing — moving any one makes the capture unusable."""
    found, verified, reason, mismatches = cap.resolve(key(**{field: "MUTATED"}))
    assert not verified, f"{field} changed but the capture still verified"
    assert field in mismatches
    assert field in reason


def test_stale_capture_cannot_authorise_promotion(saved):
    """The end-to-end consequence: a mismatched capture blocks the gate."""
    from apps.api.contracts import ArmMetrics
    from apps.api.gate import PairOutcome, evaluate

    _, verified, reason, _ = cap.resolve(key(agent_config_hash="DIFFERENT"))
    assert not verified

    clean = ArmMetrics(
        double_refund_rate=0.0, duplicate_confirmation_rate=0.0,
        premature_escalation_rate=0.0, resolution_rate=1.0, avg_turns=3.0,
        unsafe_effects=0, external_calls_executed=0,
    )
    result = evaluate(
        target_failure="double_refund",
        baseline_target=ArmMetrics(**{**clean.model_dump(), "double_refund_rate": 1.0}),
        candidate_target=clean,
        pairs=[
            PairOutcome("t1", "target", False, True, ["double_refund"], []),
            PairOutcome("c1", "control", True, True, [], []),
        ],
        candidate_unsafe_effects=0,
        candidate_external_calls=0,
        shadowed_effects=10,
        provenance_ok=verified,
        provenance_detail=reason,
    )
    assert not result.promotable, "a stale capture must not be promotable"
    assert next(c for c in result.checks if c.id == "provenance").status == "fail"


def test_missing_capture_raises_rather_than_inventing_one(tmp_path, monkeypatch):
    monkeypatch.setattr(cap.paths, "CAPTURES", tmp_path)
    found, verified, reason, _ = cap.resolve(key(task="never_captured"))
    assert found is None and not verified
    assert "No capture exists" in reason


def test_schema_validation_rejects_a_malformed_output():
    from apps.api.llm.tasks import DIAGNOSE_SCHEMA

    good = {
        "verdict": "failure",
        "root_cause": "a", "mechanism": "b", "why_it_recurs": "c",
        "cited_trace_ids": ["tr_1"], "confidence": "high",
        "remediation_kind": "config", "remediation_summary": "d",
    }
    runner.validate(good, DIAGNOSE_SCHEMA)

    with pytest.raises(runner.SchemaViolation):
        runner.validate({**good, "confidence": "certain"}, DIAGNOSE_SCHEMA)
    with pytest.raises(runner.SchemaViolation):
        runner.validate({**good, "verdict": "probably_fine"}, DIAGNOSE_SCHEMA)
    with pytest.raises(runner.SchemaViolation):
        runner.validate({k: v for k, v in good.items() if k != "mechanism"}, DIAGNOSE_SCHEMA)


def test_whole_journey_works_with_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(app)

    assert client.get("/api/health").json()["live_available"] is False
    assert client.get("/api/agent").status_code == 200

    disc = client.post("/api/discovery/run").json()
    assert len(disc["patterns"]) >= 3

    pid = disc["patterns"][0]["pattern_id"]
    assert client.post(f"/api/patterns/{pid}/diagnose").status_code == 200
    assert client.post(f"/api/patterns/{pid}/propose").status_code == 200
    assert client.post(f"/api/patterns/{pid}/patch").status_code == 200

    # ...and live mode is refused rather than silently falling back to a capture.
    assert client.post(f"/api/patterns/{pid}/diagnose", params={"mode": "live"}).status_code == 409


def test_every_pattern_still_has_a_verified_diagnosis_capture():
    """Guards the failure mode that adding one contract field caused.

    Capture provenance hashes the task's inputs. Anything that widens those
    inputs — even a presentational field annotated back onto a pattern card —
    changes the hash and silently invalidates every capture, which shows up as
    the demo falling back to fixtures. This asserts the committed captures still
    match what the code would ask for today.
    """
    from apps.api import services
    from apps.api.detect import pipeline

    if not any(paths_captures().glob("diagnose_pattern/*.json")):
        pytest.skip("no captures committed")

    stale = []
    for p in pipeline.discover().patterns:
        res = services.diagnose(p.pattern_id, "captured")
        if not res["provenance"]["verified"]:
            stale.append((p.pattern_id, res["provenance"]["stale_reason"]))

    assert not stale, "captures no longer match the current execution: " + "; ".join(
        f"{pid}: {reason}" for pid, reason in stale
    )


def paths_captures():
    from apps.api import paths

    return paths.CAPTURES
