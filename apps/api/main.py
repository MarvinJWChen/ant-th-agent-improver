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

from apps.api import devdata, paths, services, store
from apps.api.replay import engine, world

app = FastAPI(title="Agent Improver", version="0.1.0")

AGENT_NAME = "support-refund-agent"


def live_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _subsystems() -> dict[str, str]:
    """'real' means executed on request; 'fixture' means still stubbed."""
    return {
        "corpus": "real" if store.corpus_available() else "fixture",
        "discovery": "real" if store.corpus_available() else "fixture",
        "llm_captured": "real" if any(paths.CAPTURES.glob("*/*.json")) else "fixture",
        "replay": "real" if store.corpus_available() else "fixture",
        "gate": "real" if store.corpus_available() else "fixture",
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


def _discovery(force: bool) -> dict:
    real = devdata.try_real_discovery(force=force)
    if real is None:
        return devdata.discovery()
    return services.annotate(real)


@app.post("/api/discovery/run")
def run_discovery(force: bool = False):
    return _discovery(force)


@app.get("/api/discovery")
def get_discovery():
    return _discovery(False)


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


def _require_live(mode: str) -> None:
    if mode == "live" and not live_available():
        raise HTTPException(409, "Live inference unavailable: ANTHROPIC_API_KEY is not set.")


def _llm(fn, fallback, *args):
    """Real path when the corpus exists; development fixture otherwise."""
    if not store.corpus_available():
        return fallback(*args)
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/patterns/{pattern_id}/diagnose")
def diagnose(pattern_id: str, mode: Literal["captured", "live"] = "captured"):
    _require_live(mode)
    return _llm(services.diagnose, devdata.diagnose, pattern_id, mode)


@app.post("/api/patterns/{pattern_id}/propose")
def propose(pattern_id: str, mode: Literal["captured", "live"] = "captured"):
    _require_live(mode)
    return _llm(services.propose, devdata.propose, pattern_id, mode)


@app.post("/api/patterns/{pattern_id}/patch")
def patch(pattern_id: str, mode: Literal["captured", "live"] = "captured"):
    _require_live(mode)
    return _llm(services.patch, devdata.patch, pattern_id, mode)


# ------------------------------------------------------------------ replay


@app.post("/api/replay/run")
def replay_run(
    pattern_id: str,
    candidate_version: str,
    mode: Literal["captured", "live"] = "captured",
    size: int = 12,
):
    _require_live(mode)
    if not store.corpus_available():
        return devdata.replay_run(pattern_id, candidate_version, mode)
    try:
        return engine.run_replay(pattern_id, candidate_version, mode, size).model_dump()
    except engine.NoCandidateRun as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/replay/{run_id}")
def replay_get(run_id: str):
    run = engine.RUNS.get(run_id)
    if run is not None:
        return run.model_dump()
    res = devdata.replay_get(run_id)
    if res is None:
        raise HTTPException(404, f"no such replay run: {run_id}")
    return res


@app.get("/api/replay/{run_id}/pair/{trace_id}")
def replay_pair(run_id: str, trace_id: str):
    res = replay_get(run_id)
    for p in res["pairs"]:
        if p["trace_id"] == trace_id:
            return p
    raise HTTPException(404, f"trace {trace_id} not in run {run_id}")


@app.post("/api/replay/{run_id}/promote")
def replay_promote(run_id: str):
    if run_id in engine.RUNS:
        return engine.promote(run_id)
    res = devdata.promote(run_id)
    if res is None:
        raise HTTPException(404, f"no such replay run: {run_id}")
    return res


# ------------------------------------------------------------------ demo reset


@app.post("/api/demo/reset")
def reset_demo():
    """Return the deployment to the state a fresh visitor sees.

    Rehearsing the demo ends with a promoted config, and until now the only way
    back to the baseline was a redeploy. This undoes exactly the things the
    journey changes — the active config, the generated candidates, the replay
    runs held in memory, and the world clones left on disk — and touches nothing
    that took real inference or real time to produce: the trace corpus, the
    frozen worlds and the captures are all left alone.
    """
    if not store.corpus_available():
        raise HTTPException(409, "No corpus to reset. Seed it first.")

    configs = store.reset_configs("v1")
    runs_cleared = len(engine.RUNS)
    engine.RUNS.clear()
    clones_removed = world.purge_runs()

    # Drop the memoised discovery so the next click genuinely recomputes.
    try:
        from apps.api.detect import pipeline  # noqa: PLC0415

        pipeline._CACHE.clear()
    except ImportError:
        pass
    services._KIND_CACHE.clear()

    return {
        "reset": True,
        "active_version": store.active_config().version,
        "candidates_removed": configs["candidates_removed"],
        "replay_runs_cleared": runs_cleared,
        "clone_dirs_removed": clones_removed,
        "message": "Demo state reset to the baseline configuration.",
    }


# ------------------------------------------------------------------ static SPA

if paths.WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=paths.WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        return FileResponse(paths.WEB_DIST / "index.html")
