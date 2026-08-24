"""Baseline arm: deterministic replay of what production actually did.

We take the recorded trajectory verbatim — the same tool calls with the same
arguments, in the same order — and execute it against a clone of the world as it
stood when the trace began. No model is involved, so this arm is reproducible
and free. It answers: what effects did this trace really have?
"""
from __future__ import annotations

from apps.api.contracts import ArmRun, ArmTrajectoryStep, TraceDetail
from apps.api.replay import world as world_mod
from apps.api.replay.ledger import Ledger, UnknownEffectError
from apps.api.replay.metrics import TraceOutcome, score_arm
from apps.api.replay.tools import ToolHost


def run_baseline(trace: TraceDetail, run_id: str) -> tuple[ArmRun, TraceOutcome]:
    clone = world_mod.clone_world(trace.trace_id, run_id, "baseline")
    conn = world_mod.open_clone(clone)
    meta = world_mod.world_meta(conn)
    ledger = Ledger(run_id=run_id, arm="baseline", trace_id=trace.trace_id)
    host = ToolHost(conn, ledger, meta)

    steps: list[ArmTrajectoryStep] = []
    seq = 0
    turns = 0
    for ev in trace.events:
        if ev.type == "model_turn":
            turns += 1
            steps.append(ArmTrajectoryStep(seq=seq, kind="model_turn", text=ev.content))
            seq += 1
        elif ev.type == "tool_call" and ev.tool_name:
            args = ev.args or {}
            steps.append(
                ArmTrajectoryStep(seq=seq, kind="tool_call", tool_name=ev.tool_name, args=args)
            )
            seq += 1
            try:
                result = host.call(ev.tool_name, args)
            except UnknownEffectError as e:
                steps.append(
                    ArmTrajectoryStep(seq=seq, kind="agent_msg", text=f"run aborted: {e}")
                )
                seq += 1
                break
            steps.append(
                ArmTrajectoryStep(
                    seq=seq, kind="tool_result", tool_name=ev.tool_name, result=result
                )
            )
            seq += 1
        elif ev.type in ("agent_msg", "escalation"):
            steps.append(
                ArmTrajectoryStep(
                    seq=seq,
                    kind="escalation" if ev.type == "escalation" else "agent_msg",
                    text=ev.content,
                )
            )
            seq += 1

    conn.commit()
    outcome = score_arm(conn, ledger, trace.trace_id, trace.order_id, turns)
    conn.close()

    if not world_mod.source_unchanged(clone):  # pragma: no cover - safety net
        raise RuntimeError(f"frozen world for {trace.trace_id} was mutated by the baseline arm")

    arm = ArmRun(
        arm="baseline",
        trace_id=trace.trace_id,
        clone_path=str(clone.path),
        clone_sha256=clone.sha256,
        source_world_sha256=clone.source_sha256,
        execution="replayed",
        steps=steps,
        ledger=ledger.rows,
        unsafe_effects=ledger.unsafe_effects,
        external_calls_executed=ledger.external_calls_executed,
        outcome="escalated" if outcome.escalated else "resolved",
        turns=turns,
    )
    return arm, outcome
