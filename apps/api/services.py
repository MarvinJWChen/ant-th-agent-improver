"""Wiring between the HTTP routes and the executable subsystems.

Each function prefers the real path. When a required capture does not exist yet
it degrades to the development fixture, but it rewrites the provenance to say
so plainly — an unverified fixture is visible as an unverified fixture, and the
gate treats it as such.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.api import devdata, store
from apps.api.contracts import Provenance
from apps.api.detect import pipeline
from apps.api.llm import runner
from apps.api.patch.validate import apply_patch
from apps.api.patch.validate import config_hash as compute_config_hash
from apps.api.patch.validate import tools_hash as compute_tools_hash

EMAIL_TOOL_SOURCE = Path(__file__).resolve().parents[2] / "fixtures/agent_source/email_tool.py"
EXEMPLARS = 4


def _hashes() -> tuple[dict[str, Any], str, str, str]:
    cfg = store.get_config("v1").model_dump()
    tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"],
         "effect_class": t["effect_class"]}
        for t in cfg["tools"]
    ]
    bare = [{k: t[k] for k in ("name", "description", "input_schema")} for t in tools]
    return (
        {**cfg, "tools": tools},
        compute_config_hash(cfg["model"], cfg["system_prompt"], bare),
        compute_tools_hash(bare),
        store.corpus_hash(),
    )


def _pattern_inputs(pattern_id: str) -> dict[str, Any]:
    disc = pipeline.discover()
    pattern = next((p for p in disc.patterns if p.pattern_id == pattern_id), None)
    if pattern is None:
        raise KeyError(pattern_id)
    cfg, *_ = _hashes()
    traces = [
        store.get_trace(t).model_dump()
        for t in pattern.exemplar_trace_ids[:EXEMPLARS]
    ]
    return {"pattern": pattern.model_dump(), "config": cfg, "traces": traces}


def _fixture_provenance(task: str, mode: str, reason: str) -> Provenance:
    p = Provenance(**devdata._prov(task, mode))
    p.verified = False
    p.stale_reason = reason
    return p


def diagnose(pattern_id: str, mode: str) -> dict[str, Any]:
    inputs = _pattern_inputs(pattern_id)
    _, cfg_hash, t_hash, corpus_hash = _hashes()
    try:
        out, prov = runner.run(
            "diagnose_pattern", inputs, mode,
            agent_config_hash=cfg_hash, tools_hash=t_hash, corpus_hash=corpus_hash,
        )
    except runner.NoCaptureAvailable as e:
        fx = devdata.diagnose(pattern_id, mode)
        fx["provenance"] = _fixture_provenance("diagnose_pattern", mode, str(e)).model_dump()
        fx["diagnosis"]["pattern_id"] = pattern_id
        return fx
    return {
        "diagnosis": {"pattern_id": pattern_id, **out},
        "provenance": prov.model_dump(),
    }


def propose(pattern_id: str, mode: str) -> dict[str, Any]:
    """Remediation kind comes from the diagnosis, not from the clusterer."""
    diag = diagnose(pattern_id, mode)
    kind = diag["diagnosis"]["remediation_kind"]
    inputs = _pattern_inputs(pattern_id)
    _, cfg_hash, t_hash, corpus_hash = _hashes()
    base = {"diagnosis": diag["diagnosis"], "config": inputs["config"]}

    task = {
        "code": "propose_code_change",
        "process": "propose_process_change",
        "config": "propose_config_patch",
    }[kind]
    if task == "propose_code_change":
        base["source"] = EMAIL_TOOL_SOURCE.read_text()
    elif task == "propose_process_change":
        base["pattern"] = inputs["pattern"]
        base["traces"] = inputs["traces"]

    try:
        out, prov = runner.run(
            task, base, mode,
            agent_config_hash=cfg_hash, tools_hash=t_hash, corpus_hash=corpus_hash,
        )
    except runner.NoCaptureAvailable as e:
        fx = devdata.propose(pattern_id, mode)
        fx["provenance"] = _fixture_provenance(task, mode, str(e)).model_dump()
        return fx

    payload: dict[str, Any] = {"kind": kind, "code": None, "process": None, "config": None,
                               "provenance": prov.model_dump()}
    if kind == "code":
        payload["code"] = out
    elif kind == "process":
        payload["process"] = out
    else:
        payload["config"] = out
    return payload


def patch(pattern_id: str, mode: str) -> dict[str, Any]:
    """Generate candidate configs and register the in-bounds ones as versions."""
    diag = diagnose(pattern_id, mode)
    inputs = _pattern_inputs(pattern_id)
    cfg, cfg_hash, t_hash, corpus_hash = _hashes()
    try:
        out, prov = runner.run(
            "propose_config_patch",
            {"diagnosis": diag["diagnosis"], "config": cfg},
            mode,
            agent_config_hash=cfg_hash, tools_hash=t_hash, corpus_hash=corpus_hash,
        )
    except runner.NoCaptureAvailable as e:
        fx = devdata.patch(pattern_id, mode)
        fx["provenance"] = _fixture_provenance("propose_config_patch", mode, str(e)).model_dump()
        return fx

    bare = [{k: t[k] for k in ("name", "description", "input_schema")} for t in cfg["tools"]]
    base_cfg = {"model": cfg["model"], "system_prompt": cfg["system_prompt"], "tools": bare}

    candidates = []
    for i, c in enumerate(out["candidates"][:2]):
        patched, report = apply_patch(base_cfg, c["system_prompt_after"], c["tool_description_edits"])
        version = f"v2-candidate-{'ab'[i]}"
        new_hash = compute_config_hash(patched["model"], patched["system_prompt"], patched["tools"])
        if report.within_bounds:
            store.write_config(
                version=version,
                created_at=prov.created_at,
                model=patched["model"],
                system_prompt=patched["system_prompt"],
                tools=patched["tools"],
                config_hash=new_hash,
                status="candidate",
                parent_version="v1",
                notes=c["label"],
            )
        edits = []
        by_name = {t["name"]: t for t in bare}
        for e in c["tool_description_edits"]:
            if e["tool_name"] in by_name:
                edits.append({
                    "tool_name": e["tool_name"],
                    "before": by_name[e["tool_name"]]["description"],
                    "after": e["after"],
                })
        candidates.append({
            "candidate_version": version,
            "parent_version": "v1",
            "config_hash": new_hash,
            "patch": {
                "system_prompt_before": cfg["system_prompt"],
                "system_prompt_after": c["system_prompt_after"],
                "tool_description_edits": edits,
                "rationale": c["rationale"],
                "expected_effect": c["expected_effect"],
                "risks": c["risks"],
            },
            "within_edit_boundary": report.within_bounds,
            "boundary_report": report.changes + [f"REJECTED: {v}" for v in report.violations],
            "label": c["label"],
        })
    return {"candidates": candidates, "provenance": prov.model_dump()}
