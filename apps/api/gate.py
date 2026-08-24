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

# A patch that fixes its target by handing far more work to humans has not
# improved the agent, it has just moved the cost somewhere the metrics were not
# looking. Losing more than a third of the control cohort's autonomous
# resolutions counts as a regression even when every trace is still "correct".
MAX_AUTONOMY_DROP = 1 / 3


@dataclass
class PairOutcome:
    trace_id: str
    cohort: str
    baseline_pass: bool
    candidate_pass: bool
    baseline_failures: list[str]
    candidate_failures: list[str]
    baseline_resolved: bool = True
    candidate_resolved: bool = True


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

    base_auto = [p for p in controls if p.baseline_resolved]
    still_auto = [p for p in base_auto if p.candidate_resolved]
    handed_off = [p.trace_id for p in base_auto if not p.candidate_resolved]
    drop = (len(base_auto) - len(still_auto)) / len(base_auto) if base_auto else 0.0
    autonomy_lost = drop > MAX_AUTONOMY_DROP

    if regressions:
        detail = (
            f"{len(regressions)} of {len(controls)} control traces passed at baseline and "
            "fail under the candidate: "
            + ", ".join(f"{p.trace_id} ({'/'.join(p.candidate_failures)})" for p in regressions[:3])
        )
    elif autonomy_lost:
        detail = (
            f"No correctness regressions, but the candidate escalates {len(handed_off)} of "
            f"{len(base_auto)} control traces the baseline resolved on its own "
            f"({drop:.0%} drop, threshold {MAX_AUTONOMY_DROP:.0%}). It buys the fix by sending "
            f"work to humans: {', '.join(handed_off[:4])}."
        )
    else:
        detail = (
            f"All {len(base_auto)} passing control traces still pass, and autonomous "
            f"resolution held at {len(still_auto)}/{len(base_auto)}."
        )

    checks.append(
        GateCheck(
            id="control_preservation",
            label="No regression on passing controls",
            status="fail" if (regressions or autonomy_lost) else "pass",
            detail=detail,
            evidence=[p.trace_id for p in regressions] or handed_off,
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
