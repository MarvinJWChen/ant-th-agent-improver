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


def candidate_version(pattern_id: str, index: int) -> str:
    """Candidate versions are namespaced per pattern.

    Two patterns can each produce candidates, and a shared name would mean the
    second patch silently overwrote the first — including the config a captured
    counterfactual run was made against.
    """
    return f"v2-{pattern_id.lower()}-{'ab'[index]}"


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
    # `verdict` and `remediation_kind` are *outputs* of the diagnosis, annotated
    # back onto the card afterwards. Feeding them in would be circular, and —
    # because the inputs are hashed for provenance — would also invalidate every
    # existing capture the moment the annotation was added. Anything that is not
    # a genuine input to the prompt stays out of here.
    return {
        "pattern": pattern.model_dump(exclude={"verdict", "evidence_trace_ids"}),
        "config": cfg,
        "traces": traces,
    }


def _fixture_provenance(task: str, mode: str, reason: str) -> Provenance:
    p = Provenance(**devdata._prov(task, mode))
    p.verified = False
    p.stale_reason = reason
    return p


def summarize(diagnosis: dict[str, Any], mode: str) -> dict[str, Any] | None:
    """A scannable version of a diagnosis, from a cheaper model.

    Best-effort on purpose: the full diagnosis is the artifact of record, and a
    missing summary must never take the page down. It compresses text that is
    already on the page, so it is the one place where a smaller model is the
    right call.
    """
    _, cfg_hash, t_hash, corpus_hash = _hashes()
    try:
        out, prov = runner.run(
            "summarize_diagnosis", {"diagnosis": diagnosis}, mode,
            agent_config_hash=cfg_hash, tools_hash=t_hash, corpus_hash=corpus_hash,
        )
    except Exception:  # noqa: BLE001 - no capture, no key, or a bad response
        return None
    return {**out, "provenance": prov.model_dump()}


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
    diagnosis = {"pattern_id": pattern_id, **out}
    return {
        "diagnosis": diagnosis,
        "provenance": prov.model_dump(),
        "summary": summarize(diagnosis, mode),
    }


def stable_diagnosis(pattern_id: str, mode: str) -> dict[str, Any]:
    """The diagnosis a downstream task is built on must not move underneath it.

    A proposal's provenance hashes its inputs, and the diagnosis is one of them.
    If we re-ran the diagnosis live every time, each run would produce slightly
    different wording, the inputs hash would change, and the proposal captured
    against it could never validate again. So downstream tasks always read the
    captured diagnosis when one exists, and only fall back to the requested mode
    when there is nothing to read.
    """
    captured = diagnose(pattern_id, "captured")
    if captured["provenance"]["verified"]:
        return captured
    return diagnose(pattern_id, mode)


def propose(pattern_id: str, mode: str) -> dict[str, Any]:
    """Remediation kind comes from the diagnosis, not from the clusterer."""
    diag = stable_diagnosis(pattern_id, mode)
    kind = diag["diagnosis"]["remediation_kind"]
    inputs = _pattern_inputs(pattern_id)
    _, cfg_hash, t_hash, corpus_hash = _hashes()
    base = {"diagnosis": diag["diagnosis"], "config": inputs["config"]}

    if kind == "none":
        # The diagnosis judged this cluster to be correct behaviour. There is
        # nothing to propose, and inventing a remediation would be worse than
        # saying so.
        return {
            "kind": "none",
            "code": None,
            "process": None,
            "config": None,
            "provenance": diag["provenance"],
            "verdict": diag["diagnosis"].get("verdict", "expected_behaviour"),
            "explanation": diag["diagnosis"]["remediation_summary"],
        }

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
    diag = stable_diagnosis(pattern_id, mode)
    cfg, cfg_hash, t_hash, corpus_hash = _hashes()
    try:
        out, prov = runner.run(
            "propose_config_patch",
            {"diagnosis": diag["diagnosis"], "config": cfg},
            mode,
            agent_config_hash=cfg_hash, tools_hash=t_hash, corpus_hash=corpus_hash,
        )
    except runner.NoCaptureAvailable as e:
        # No capture yet. The patch *text* falls back to a development fixture and
        # is labelled unverified, but the candidate configs are still registered
        # for real so that replay, the Effect Ledger, and the gate keep running
        # against genuine configurations rather than fixtures of their own.
        fx = devdata.patch(pattern_id, mode)
        fx["provenance"] = _fixture_provenance("propose_config_patch", mode, str(e)).model_dump()
        bare = [{k: t[k] for k in ("name", "description", "input_schema")} for t in cfg["tools"]]
        base_cfg = {"model": cfg["model"], "system_prompt": cfg["system_prompt"], "tools": bare}
        for i, c in enumerate(fx["candidates"]):
            c["candidate_version"] = candidate_version(pattern_id, i)
            patched, report = apply_patch(
                base_cfg,
                c["patch"]["system_prompt_after"],
                [{"tool_name": e2["tool_name"], "after": e2["after"]}
                 for e2 in c["patch"]["tool_description_edits"]],
            )
            new_hash = compute_config_hash(
                patched["model"], patched["system_prompt"], patched["tools"]
            )
            c["config_hash"] = new_hash
            c["within_edit_boundary"] = report.within_bounds
            c["boundary_report"] = report.changes + [f"REJECTED: {v}" for v in report.violations]
            if report.within_bounds:
                store.write_config(
                    version=c["candidate_version"],
                    created_at=fx["provenance"]["created_at"],
                    model=patched["model"],
                    system_prompt=patched["system_prompt"],
                    tools=patched["tools"],
                    config_hash=new_hash,
                    status="candidate",
                    parent_version="v1",
                    notes=c["label"],
                )
        return fx

    bare = [{k: t[k] for k in ("name", "description", "input_schema")} for t in cfg["tools"]]
    base_cfg = {"model": cfg["model"], "system_prompt": cfg["system_prompt"], "tools": bare}

    candidates = []
    for i, c in enumerate(out["candidates"][:2]):
        patched, report = apply_patch(base_cfg, c["system_prompt_after"], c["tool_description_edits"])
        version = candidate_version(pattern_id, i)
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


_KIND_CACHE: dict[str, dict[str, dict[str, str]]] = {}


def captured_verdicts() -> dict[str, dict[str, str]]:
    """Verdict and remediation kind per pattern, read only from verified captures.

    Discovery stays free of any inference: this looks up what a previous
    diagnosis concluded and returns nothing for patterns that have never been
    diagnosed. It never falls back to a fixture, because an unverified guess
    shown as a category label would be worse than an empty one.
    """
    key = store.corpus_hash()
    if key in _KIND_CACHE:
        return _KIND_CACHE[key]

    _, cfg_hash, t_hash, corpus_hash = _hashes()
    out: dict[str, dict[str, str]] = {}
    for p in pipeline.discover().patterns:
        try:
            inputs = _pattern_inputs(p.pattern_id)
            res, prov = runner.run(
                "diagnose_pattern", inputs, "captured",
                agent_config_hash=cfg_hash, tools_hash=t_hash, corpus_hash=corpus_hash,
            )
        except (runner.NoCaptureAvailable, KeyError):
            continue
        if not prov.verified:
            continue
        out[p.pattern_id] = {
            "verdict": res.get("verdict", "failure"),
            "remediation_kind": res["remediation_kind"],
        }
    _KIND_CACHE[key] = out
    return out


def annotate(discovery: dict) -> dict:
    """Attach captured verdicts to the discovery result for the pattern list."""
    kinds = captured_verdicts()
    for p in discovery.get("patterns", []):
        k = kinds.get(p["pattern_id"])
        if k:
            p["verdict"] = k["verdict"]
            p["remediation_kind"] = k["remediation_kind"]
    return discovery
