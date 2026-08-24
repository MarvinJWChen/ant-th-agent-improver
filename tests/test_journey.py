"""One complete pass over every CTA the audience can click.

Not a coverage exercise — this is the check that the demo path itself still
works after a change, from a cold app instance.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api import store
from apps.api.main import app

pytestmark = pytest.mark.skipif(not store.corpus_available(), reason="corpus not seeded")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_step1_overview(client):
    r = client.get("/api/agent")
    assert r.status_code == 200
    body = r.json()
    assert body["corpus"]["total_traces"] == 1000
    assert body["active_config"]["version"] == "v1"
    assert len(body["active_config"]["tools"]) == 5
    # Every tool must declare a blast radius, or replay could not fail closed.
    assert all(t["effect_class"] != "unknown" for t in body["active_config"]["tools"])


def test_step2_discovery_is_computed_not_stored(client):
    a = client.post("/api/discovery/run").json()
    b = client.post("/api/discovery/run").json()
    assert a["n_traces_scanned"] == 1000
    assert len(a["patterns"]) >= 3
    assert a["corpus_hash"] == b["corpus_hash"], "same corpus must give the same result"
    assert a["n_flagged"] > 0
    assert 0.0 < a["silhouette"] <= 1.0


def test_step2_flagged_traces_carry_evidence(client):
    disc = client.get("/api/discovery").json()
    for f in disc["flagged"][:20]:
        assert f["hits"], f"{f['trace']['trace_id']} was flagged with no evidence"
        for h in f["hits"]:
            assert h["detail"], "every hit must be explainable"


def test_step3_pattern_and_trace_evidence(client):
    disc = client.get("/api/discovery").json()
    pid = disc["patterns"][0]["pattern_id"]
    p = client.get(f"/api/patterns/{pid}")
    assert p.status_code == 200
    exemplar = p.json()["pattern"]["exemplar_trace_ids"][0]

    t = client.get(f"/api/traces/{exemplar}")
    assert t.status_code == 200
    assert t.json()["events"], "an exemplar with no events proves nothing"


def test_step3_diagnosis_and_patch(client):
    disc = client.get("/api/discovery").json()
    pid = disc["patterns"][0]["pattern_id"]

    d = client.post(f"/api/patterns/{pid}/diagnose")
    assert d.status_code == 200
    assert d.json()["diagnosis"]["remediation_kind"] in ("config", "code", "process")
    assert "verified" in d.json()["provenance"]

    pt = client.post(f"/api/patterns/{pid}/patch")
    assert pt.status_code == 200
    for c in pt.json()["candidates"]:
        assert c["boundary_report"], "a patch must report what it changed"


def test_step4_replay_never_silently_fabricates(client):
    """Either a real replay runs, or the API says plainly why it cannot."""
    disc = client.get("/api/discovery").json()
    pid = disc["patterns"][0]["pattern_id"]
    client.post(f"/api/patterns/{pid}/patch")

    r = client.post(
        "/api/replay/run",
        params={"pattern_id": pid, "candidate_version": "v2-candidate-b", "size": 2},
    )
    assert r.status_code in (200, 409)
    if r.status_code == 409:
        assert "captured counterfactual run" in r.json()["detail"]
        return

    run = r.json()
    assert run["world_isolation"]["source_worlds_mutated"] == 0
    assert run["candidate_metrics"]["external_calls_executed"] == 0
    assert len(run["gate"]["checks"]) == 4
    for pair in run["pairs"]:
        assert pair["baseline"]["clone_sha256"] == pair["candidate"]["clone_sha256"]
        assert pair["baseline"]["clone_path"] != pair["candidate"]["clone_path"]


def test_step5_proposals(client):
    disc = client.get("/api/discovery").json()
    for pattern in disc["patterns"][:2]:
        r = client.post(f"/api/patterns/{pattern['pattern_id']}/propose")
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] in ("config", "code", "process")
        assert body[body["kind"]] is not None, "the proposal body must match its kind"


def test_live_mode_refuses_without_a_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/patterns/P1/diagnose", params={"mode": "live"})
    assert r.status_code == 409
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_spa_deep_links_do_not_404(client):
    if not (store.paths.WEB_DIST / "index.html").exists():
        pytest.skip("SPA not built")
    for path in ("/", "/discovery", "/patterns/P1", "/replay/P1", "/proposals"):
        assert client.get(path).status_code == 200, f"{path} must serve the SPA shell"
