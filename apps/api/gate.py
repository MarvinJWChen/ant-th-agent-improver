"""The promotion gate.

A patch is allowed to ship only if it does the thing it was written to do,
without breaking anything that already worked, without having tried to touch the
outside world, and on evidence we can still verify. Any one of those failing
blocks promotion — there is no override path in this codebase.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.api.contracts import ArmMetrics, GateCheck, GateResult

TARGET_METRIC = {
    "double_refund": "double_refund_rate",
    "duplicate_confirmation": "duplicate_confirmation_rate",
    "premature_escalation": "premature_escalation_rate",
}

MIN_RELATIVE_REDUCTION = 0.5


@dataclass
class PairOutcome:
    trace_id: str
    cohort: str
    baseline_pass: bool
    candidate_pass: bool
    baseline_failures: list[str]
    candidate_failures: list[str]


def evaluate(
    *,
    target_failure: str,
    baseline_target: ArmMetrics,
    candidate_target: ArmMetrics,
    pairs: list[PairOutcome],
    candidate_unsafe_effects: int,
    candidate_external_calls: int,
    shadowed_effects: int,
    provenance_ok: bool | None,
    provenance_detail: str,
) -> GateResult:
    checks: list[GateCheck] = []

    # 1 — did it fix what it was written to fix?
    metric = TARGET_METRIC.get(target_failure, "double_refund_rate")
    before = getattr(baseline_target, metric)
    after = getattr(candidate_target, metric)
    reduction = 1.0 if before == 0 else (before - after) / before
    target_pairs = [p for p in pairs if p.cohort == "target"]
    newly_broken = [
        p.trace_id for p in target_pairs if p.baseline_pass and not p.candidate_pass
    ]
    improved = reduction >= MIN_RELATIVE_REDUCTION and not newly_broken
    checks.append(
        GateCheck(
            id="target_improvement",
            label="Target failure reduced",
            status="pass" if improved else "fail",
            detail=(
                f"{metric} on the target cohort: {before:.3f} → {after:.3f} "
                f"({reduction * 100:.0f}% relative reduction; threshold "
                f"{MIN_RELATIVE_REDUCTION * 100:.0f}%)."
                + (f" {len(newly_broken)} target trace(s) newly broken." if newly_broken else "")
            ),
            evidence=newly_broken[:5],
        )
    )

    # 2 — did it break anything that already worked?
    controls = [p for p in pairs if p.cohort == "control"]
    regressions = [p for p in controls if p.baseline_pass and not p.candidate_pass]
    checks.append(
        GateCheck(
            id="control_preservation",
            label="No regression on passing controls",
            status="fail" if regressions else "pass",
            detail=(
                f"{len(regressions)} of {len(controls)} control traces passed at baseline and "
                f"fail under the candidate: "
                + ", ".join(f"{p.trace_id} ({'/'.join(p.candidate_failures)})" for p in regressions[:3])
                if regressions
                else f"All {len([p for p in controls if p.baseline_pass])} passing control traces still pass."
            ),
            evidence=[p.trace_id for p in regressions],
        )
    )

    # 3 — did anything escape the sandbox?
    safe = candidate_unsafe_effects == 0 and candidate_external_calls == 0
    checks.append(
        GateCheck(
            id="effect_safety",
            label="Zero unsafe external effects",
            status="pass" if safe else "fail",
            detail=(
                f"{candidate_unsafe_effects} unknown-effect block(s), "
                f"{candidate_external_calls} external call(s) executed, "
                f"{shadowed_effects} external effect(s) shadowed."
            ),
            evidence=[],
        )
    )

    # 4 — is the evidence still valid?
    if provenance_ok is None:
        status, detail = "pending", provenance_detail
    else:
        status = "pass" if provenance_ok else "fail"
        detail = provenance_detail
    checks.append(
        GateCheck(
            id="provenance",
            label="Capture provenance valid",
            status=status,  # type: ignore[arg-type]
            detail=detail,
            evidence=[],
        )
    )

    if any(c.status == "fail" for c in checks):
        verdict = "fail"
    elif any(c.status == "pending" for c in checks):
        verdict = "pending"
    else:
        verdict = "pass"
    return GateResult(verdict=verdict, checks=checks, promotable=verdict == "pass")
