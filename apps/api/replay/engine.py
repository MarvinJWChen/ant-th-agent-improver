"""Replay orchestration.

Builds two cohorts, runs both arms over every trace in them, measures each arm
the same way, and hands the result to the gate. The control cohort exists
because a patch that fixes its target while quietly breaking healthy traffic is
not an improvement, and nothing else in the system would notice.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from apps.api import gate as gate_mod
from apps.api import store
from apps.api.contracts import (
    ArmMetrics,
    Provenance,
    ReplayRun,
    TracePairResult,
)
from apps.api.detect import pipeline
from apps.api.llm import capture as cap
from apps.api.patch.validate import config_hash as compute_config_hash
from apps.api.patch.validate import tools_hash as compute_tools_hash
from apps.api.replay import counterfactual as cf
from apps.api.replay import world as world_mod
from apps.api.replay.baseline import run_baseline
from apps.api.replay.metrics import aggregate

COHORT_SIZE = 12
RUNS: dict[str, ReplayRun] = {}


class NoCandidateRun(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_cohorts(pattern_id: str, size: int = COHORT_SIZE) -> tuple[list[str], list[str]]:
    """Target = traces in the pattern. Control = healthy traffic plus the other patterns.

    Controls deliberately include traces from the *other* discovered patterns:
    a fix for one failure must not be allowed to make a different known failure
    worse just because nobody was looking at it.
    """
    disc = pipeline.discover()
    pattern = next((p for p in disc.patterns if p.pattern_id == pattern_id), None)
    if pattern is None:
        raise KeyError(f"no such pattern: {pattern_id}")
    cid = pattern.impact["cluster_id"]

    members = [f for f in disc.flagged if f.cluster_id == cid]
    members.sort(key=lambda f: f.trace.trace_id)
    target = [f.trace.trace_id for f in members[:size]]

    # The control cohort has to be mostly traffic that *passes* today — a patch
    # can only be caught regressing something that currently works. One trace
    # from each neighbouring pattern keeps an eye on the other known failures
    # without crowding out the healthy majority.
    flagged_ids = {f.trace.trace_id for f in disc.flagged}
    others: list[str] = []
    for p in disc.patterns:
        if p.pattern_id == pattern_id:
            continue
        peers = sorted(
            (f.trace.trace_id for f in disc.flagged if f.cluster_id == p.impact["cluster_id"])
        )
        others.extend(peers[:1])
    others = others[: max(size // 3, 1)]

    unflagged = [t for t in store.all_trace_ids() if t not in flagged_ids]
    n_healthy = max(size - len(others), 0)
    stride = max(len(unflagged) // max(n_healthy, 1), 1)
    healthy = unflagged[::stride][:n_healthy]

    control = (others + healthy)[:size]
    return target, control


def _dominant_failure(outcomes) -> str:
    c = Counter(lbl for o in outcomes for lbl in o.failure_labels())
    return c.most_common(1)[0][0] if c else "double_refund"


def run_replay(
    pattern_id: str,
    candidate_version: str,
    mode: str = "captured",
    size: int = COHORT_SIZE,
) -> ReplayRun:
    baseline_cfg = store.get_config("v1")
    candidate_cfg = store.get_config(candidate_version)
    cand = candidate_cfg.model_dump()
    cand_tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in cand["tools"]
    ]
    cfg_hash = compute_config_hash(cand["model"], cand["system_prompt"], cand_tools)
    t_hash = compute_tools_hash(cand_tools)
    corpus_hash = store.corpus_hash()

    target_ids, control_ids = build_cohorts(pattern_id, size)
    run_id = f"run_{pattern_id}_{candidate_version}_{mode}"

    pairs: list[TracePairResult] = []
    gate_pairs: list[gate_mod.PairOutcome] = []
    base_target, cand_target = [], []
    base_all, cand_all = [], []
    unverified: list[str] = []
    stale_reasons: list[str] = []
    shadowed = 0

    for cohort, ids in (("target", target_ids), ("control", control_ids)):
        for tid in ids:
            trace = store.get_trace(tid)

            b_arm, b_out = run_baseline(trace, run_id)

            # Provenance uses the world's content hash so a capture stays valid
            # across machines; the byte hashes below prove clone isolation.
            world_hash = world_mod.content_hash(world_mod.paths.world_path(tid))
            key = cf.capture_key(
                trace,
                {**cand, "tools": cand_tools},
                config_hash=cfg_hash,
                tools_hash=t_hash,
                corpus_hash=corpus_hash,
                world_hash=world_hash,
            )

            if mode == "live":
                c_arm, c_out, payload = cf.run_candidate_live(
                    trace, run_id, {**cand, "tools": cand_tools}
                )
                cap.save(key, payload, notes="Live counterfactual run triggered from the browser.")
            else:
                found, verified, reason, _ = cap.resolve(key)
                if found is None:
                    raise NoCandidateRun(
                        f"No captured counterfactual run for {tid} under {candidate_version}. "
                        "Cached mode cannot substitute the original trace's model outputs: "
                        "the candidate has a different configuration and may take a different "
                        "trajectory, so it must be re-executed. " + reason
                    )
                c_arm, c_out = cf.rehydrate(found.output)
                if not verified:
                    unverified.append(tid)
                    stale_reasons.append(reason)

            shadowed += sum(1 for r in c_arm.ledger if r.disposition == "SHADOWED")
            base_all.append(b_out)
            cand_all.append(c_out)
            if cohort == "target":
                base_target.append(b_out)
                cand_target.append(c_out)

            diverged = [s.tool_name for s in b_arm.steps if s.kind == "tool_call"] != [
                s.tool_name for s in c_arm.steps if s.kind == "tool_call"
            ]
            pairs.append(
                TracePairResult(
                    trace_id=tid,
                    cohort=cohort,  # type: ignore[arg-type]
                    baseline=b_arm,
                    candidate=c_arm,
                    trajectory_diverged=diverged,
                    baseline_pass=b_out.passed,
                    candidate_pass=c_out.passed,
                    regression=b_out.passed and not c_out.passed,
                )
            )
            gate_pairs.append(
                gate_mod.PairOutcome(
                    trace_id=tid,
                    cohort=cohort,
                    baseline_pass=b_out.passed,
                    candidate_pass=c_out.passed,
                    baseline_failures=b_out.failure_labels(),
                    candidate_failures=c_out.failure_labels(),
                )
            )

    target_failure = _dominant_failure(base_target)
    baseline_metrics: ArmMetrics = aggregate(base_all)
    candidate_metrics: ArmMetrics = aggregate(cand_all)

    if mode == "live":
        prov_ok, prov_detail = True, (
            f"{len(target_ids) + len(control_ids)} counterfactual runs executed live and captured."
        )
    elif unverified:
        prov_ok = False
        prov_detail = (
            f"{len(unverified)} captured run(s) do not match this execution — "
            f"{stale_reasons[0]} Promotion is blocked on stale evidence."
        )
    else:
        prov_ok = True
        prov_detail = (
            f"All {len(pairs)} captured counterfactual runs match this candidate config, "
            "tool surface, corpus, frozen world, and agent-loop version."
        )

    result = gate_mod.evaluate(
        target_failure=target_failure,
        baseline_target=aggregate(base_target),
        candidate_target=aggregate(cand_target),
        pairs=gate_pairs,
        candidate_unsafe_effects=sum(o.unsafe_effects for o in cand_all),
        candidate_external_calls=sum(o.external_calls_executed for o in cand_all),
        shadowed_effects=shadowed,
        provenance_ok=prov_ok,
        provenance_detail=prov_detail,
    )

    sources_intact = all(
        world_mod.sha256_file(world_mod.paths.world_path(p.trace_id)) == p.baseline.source_world_sha256
        for p in pairs
    )

    run = ReplayRun(
        run_id=run_id,
        pattern_id=pattern_id,
        candidate_version=candidate_version,
        baseline_version=baseline_cfg.version,
        mode=mode,  # type: ignore[arg-type]
        started_at=_now(),
        finished_at=_now(),
        cohort_target=target_ids,
        cohort_control=control_ids,
        world_isolation={
            "worlds_frozen": len(pairs),
            "clones_created": len(pairs) * 2,
            "source_worlds_mutated": 0 if sources_intact else -1,
            "distinct_clone_hashes": len({p.baseline.clone_sha256 for p in pairs}
                                         | {p.candidate.clone_sha256 for p in pairs}),
            "external_effects_shadowed": shadowed,
            "note": "Each arm runs against its own file-level copy of the frozen world; "
                    "the recorded world is verified unchanged after both arms complete.",
        },
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        pairs=pairs,
        gate=result,
        provenance=Provenance(
            mode=mode,  # type: ignore[arg-type]
            task=cf.CAPTURE_TASK,
            task_version="2026-08-24.1",
            model=cand["model"],
            created_at=_now(),
            verified=prov_ok,
            stale_reason=None if prov_ok else prov_detail,
            hashes={
                "agent_config_hash": cfg_hash,
                "tools_hash": t_hash,
                "corpus_hash": corpus_hash,
            },
            expected_hashes=None,
            latency_ms=None,
        ),
        promoted=False,
    )
    RUNS[run_id] = run
    return run


def promote(run_id: str) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if run is None:
        raise KeyError(run_id)
    if not run.gate.promotable:
        return {
            "promoted": False,
            "active_version": store.active_config().version,
            "message": "Promotion blocked: the gate did not pass.",
            "gate": run.gate.model_dump(),
        }
    store.demote_active()
    store.set_status(run.candidate_version, "active")
    run.promoted = True
    return {
        "promoted": True,
        "active_version": run.candidate_version,
        "message": f"{run.candidate_version} promoted to active configuration.",
        "gate": run.gate.model_dump(),
    }
