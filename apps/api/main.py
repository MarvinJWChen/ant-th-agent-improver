"""Agent Improver API.

Every route is contract-stable. Handlers prefer the real executable path and
fall back to development fixtures only while a subsystem is still being built;
`GET /api/health` reports exactly which subsystems are real right now, so the
demo can never quietly claim more than it does.
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api import devdata, paths, store

app = FastAPI(title="Agent Improver", version="0.1.0")

AGENT_NAME = "support-refund-agent"


def live_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _subsystems() -> dict[str, str]:
    """'real' means executed on request; 'fixture' means still stubbed."""
    return {
        "corpus": "real" if store.corpus_available() else "fixture",
        "discovery": "real" if devdata.has_real("discovery") else "fixture",
        "llm_captured": "real" if devdata.has_real("llm") else "fixture",
        "replay": "real" if devdata.has_real("replay") else "fixture",
        "gate": "real" if devdata.has_real("gate") else "fixture",
    }


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "live_available": live_available(),
        "subsystems": _subsystems(),
    }


# ------------------------------------------------------------------ overview


@app.get("/api/agent")
def agent_overview():
    if not store.corpus_available():
        return devdata.agent_overview(live_available())
    cfg = store.active_config()
    return {
        "agent_name": AGENT_NAME,
        "active_config": cfg.model_dump(),
        "corpus": store.corpus_stats().model_dump(),
        "live_available": live_available(),
    }


@app.get("/api/configs")
def list_configs():
    if not store.corpus_available():
        return devdata.configs()
    return [c.model_dump() for c in store.list_configs()]


@app.get("/api/configs/{version}")
def get_config(version: str):
    if not store.corpus_available():
        return devdata.config(version)
    try:
        return store.get_config(version).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


# ------------------------------------------------------------------ traces


@app.get("/api/traces")
def list_traces(
    limit: int = Query(50, le=500),
    offset: int = 0,
    outcome: str | None = None,
):
    if not store.corpus_available():
        return devdata.traces(limit)
    return [t.model_dump() for t in store.list_traces(limit, offset, outcome)]


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str):
    if not store.corpus_available():
        return devdata.trace(trace_id)
    try:
        return store.get_trace(trace_id).model_dump()
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


# ------------------------------------------------------------------ discovery


@app.post("/api/discovery/run")
def run_discovery(force: bool = False):
    real = devdata.try_real_discovery(force=force)
    if real is not None:
        return real
    return devdata.discovery()


@app.get("/api/discovery")
def get_discovery():
    real = devdata.try_real_discovery(force=False)
    if real is not None:
        return real
    return devdata.discovery()


@app.get("/api/patterns/{pattern_id}")
def get_pattern(pattern_id: str):
    res = get_discovery()
    for p in res["patterns"]:
        if p["pattern_id"] == pattern_id:
            flagged = [f for f in res["flagged"] if f.get("cluster_id") == p.get("cluster_id")]
            return {
                "pattern": p,
                "flagged": flagged[:40],
                "discovery_meta": {
                    k: res[k]
                    for k in (
                        "computed_at",
                        "n_traces_scanned",
                        "n_flagged",
                        "cluster_k",
                        "silhouette",
                        "anomaly_threshold",
                    )
                },
            }
    raise HTTPException(404, f"no such pattern: {pattern_id}")


# ------------------------------------------------------------------ LLM tasks


@app.post("/api/patterns/{pattern_id}/diagnose")
def diagnose(pattern_id: str, mode: Literal["captured", "live"] = "captured"):
    if mode == "live" and not live_available():
        raise HTTPException(409, "Live inference unavailable: ANTHROPIC_API_KEY is not set.")
    return devdata.diagnose(pattern_id, mode)


@app.post("/api/patterns/{pattern_id}/propose")
def propose(pattern_id: str, mode: Literal["captured", "live"] = "captured"):
    if mode == "live" and not live_available():
        raise HTTPException(409, "Live inference unavailable: ANTHROPIC_API_KEY is not set.")
    return devdata.propose(pattern_id, mode)


@app.post("/api/patterns/{pattern_id}/patch")
def patch(pattern_id: str, mode: Literal["captured", "live"] = "captured"):
    if mode == "live" and not live_available():
        raise HTTPException(409, "Live inference unavailable: ANTHROPIC_API_KEY is not set.")
    return devdata.patch(pattern_id, mode)


# ------------------------------------------------------------------ replay


@app.post("/api/replay/run")
def replay_run(
    pattern_id: str,
    candidate_version: str,
    mode: Literal["captured", "live"] = "captured",
):
    if mode == "live" and not live_available():
        raise HTTPException(409, "Live inference unavailable: ANTHROPIC_API_KEY is not set.")
    return devdata.replay_run(pattern_id, candidate_version, mode)


@app.get("/api/replay/{run_id}")
def replay_get(run_id: str):
    res = devdata.replay_get(run_id)
    if res is None:
        raise HTTPException(404, f"no such replay run: {run_id}")
    return res


@app.get("/api/replay/{run_id}/pair/{trace_id}")
def replay_pair(run_id: str, trace_id: str):
    res = devdata.replay_get(run_id)
    if res is None:
        raise HTTPException(404, f"no such replay run: {run_id}")
    for p in res["pairs"]:
        if p["trace_id"] == trace_id:
            return p
    raise HTTPException(404, f"trace {trace_id} not in run {run_id}")


@app.post("/api/replay/{run_id}/promote")
def replay_promote(run_id: str):
    res = devdata.promote(run_id)
    if res is None:
        raise HTTPException(404, f"no such replay run: {run_id}")
    return res


# ------------------------------------------------------------------ static SPA

if paths.WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=paths.WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        return FileResponse(paths.WEB_DIST / "index.html")
