"""Candidate arm: what the patched agent would have done.

The candidate is not a replay. Its configuration changed, so its trajectory may
change too — it may call different tools, in a different order, or stop earlier.
The only way to know is to run it, which is exactly what this does, against its
own clone of the same frozen world the baseline saw.

Cached mode returns a previously captured *live counterfactual run* — the real
trajectory and the real ledger that run produced. It never replays the original
trace's model outputs, because those came from a different configuration and
would answer the wrong question.
"""
from __future__ import annotations

from typing import Any

from apps.api.agent_loop import AGENT_LOOP_VERSION, run_agent
from apps.api.contracts import ArmRun, ArmTrajectoryStep, TraceDetail
from apps.api.llm import capture as cap
from apps.api.replay import world as world_mod
from apps.api.replay.ledger import Ledger, UnknownEffectError
from apps.api.replay.metrics import TraceOutcome, score_arm
from apps.api.replay.tools import ToolHost

CAPTURE_TASK = "counterfactual_run"


def _first_user_message(trace: TraceDetail) -> str:
    for ev in trace.events:
        if ev.type == "user_msg" and ev.content:
            return ev.content
    return f"I need help with order {trace.order_id}."


def capture_key(
    trace: TraceDetail,
    candidate_config: dict[str, Any],
    *,
    config_hash: str,
    tools_hash: str,
    corpus_hash: str,
    world_hash: str,
) -> cap.ProvenanceKey:
    """Provenance for one candidate run against one frozen world.

    Includes the world hash and the agent-loop version, so a capture cannot be
    reused after the world it ran against or the loop that produced it changes.
    """
    return cap.ProvenanceKey(
        task=CAPTURE_TASK,
        task_version="2026-08-24.1",
        model=candidate_config["model"],
        prompt_hash=cap.sha_text(_first_user_message(trace)),
        inputs_hash=cap.sha({"trace_id": trace.trace_id}),
        output_schema_hash=cap.sha({"shape": "ArmRun"}),
        agent_config_hash=config_hash,
        tools_hash=tools_hash,
        corpus_hash=corpus_hash,
        world_hash=world_hash,
        loop_version=AGENT_LOOP_VERSION,
    )


def run_candidate_live(
    trace: TraceDetail,
    run_id: str,
    candidate_config: dict[str, Any],
) -> tuple[ArmRun, TraceOutcome, dict[str, Any]]:
    clone = world_mod.clone_world(trace.trace_id, run_id, "candidate")
    conn = world_mod.open_clone(clone)
    meta = world_mod.world_meta(conn)
    ledger = Ledger(run_id=run_id, arm="candidate", trace_id=trace.trace_id)
    host = ToolHost(conn, ledger, meta)

    result = run_agent(
        system_prompt=candidate_config["system_prompt"],
        tools=candidate_config["tools"],
        user_message=_first_user_message(trace),
        host=host,
    )

    conn.commit()
    outcome = score_arm(conn, ledger, trace.trace_id, trace.order_id, result.turns)
    conn.close()
    after = world_mod.sha256_file(clone.path)

    if not world_mod.source_unchanged(clone):  # pragma: no cover - safety net
        raise RuntimeError(f"frozen world for {trace.trace_id} was mutated by the candidate arm")

    arm = ArmRun(
        arm="candidate",
        trace_id=trace.trace_id,
        clone_path=str(clone.path),
        clone_sha256=clone.sha256,
        clone_sha256_after=after,
        source_world_sha256=clone.source_sha256,
        execution="re-executed",
        steps=result.steps,
        ledger=ledger.rows,
        unsafe_effects=ledger.unsafe_effects,
        external_calls_executed=ledger.external_calls_executed,
        outcome="escalated" if outcome.escalated else "resolved",
        turns=result.turns,
    )
    payload = {
        "arm": arm.model_dump(),
        "outcome": outcome.as_dict(),
        "stopped_because": result.stopped_because,
    }
    return arm, outcome, payload


def rehydrate(
    trace: TraceDetail, run_id: str, payload: dict[str, Any]
) -> tuple[ArmRun, TraceOutcome]:
    """Re-execute a captured counterfactual run against a fresh clone.

    The capture supplies the *trajectory* — the tool calls the live agent chose
    under the patched configuration. Those are replayed here against a new copy
    of the frozen world, and the ledger, the final state, and every metric are
    produced by that execution rather than read back from the file.

    This is the distinction the whole design turns on. We are replaying the
    captured counterfactual run's own model outputs, never the original trace's:
    those came from a different configuration and would answer a different
    question. And because the numbers are recomputed, changing how an outcome is
    measured changes what the captures report — a stored metric would silently
    keep reporting the old definition.
    """
    steps = [ArmTrajectoryStep(**s) for s in payload["arm"]["steps"]]

    clone = world_mod.clone_world(trace.trace_id, run_id, "candidate")
    conn = world_mod.open_clone(clone)
    ledger = Ledger(run_id=run_id, arm="candidate", trace_id=trace.trace_id)
    host = ToolHost(conn, ledger, world_mod.world_meta(conn))

    replayed: list[ArmTrajectoryStep] = []
    seq = 0
    turns = 0
    for step in steps:
        if step.kind == "model_turn":
            turns += 1
            replayed.append(ArmTrajectoryStep(seq=seq, kind="model_turn", text=step.text))
            seq += 1
        elif step.kind == "tool_call" and step.tool_name:
            replayed.append(
                ArmTrajectoryStep(
                    seq=seq, kind="tool_call", tool_name=step.tool_name, args=step.args
                )
            )
            seq += 1
            try:
                result = host.call(step.tool_name, step.args or {})
            except UnknownEffectError as e:
                replayed.append(
                    ArmTrajectoryStep(seq=seq, kind="agent_msg", text=f"run aborted: {e}")
                )
                seq += 1
                break
            replayed.append(
                ArmTrajectoryStep(
                    seq=seq, kind="tool_result", tool_name=step.tool_name, result=result
                )
            )
            seq += 1
        elif step.kind in ("agent_msg", "escalation"):
            replayed.append(ArmTrajectoryStep(seq=seq, kind=step.kind, text=step.text))
            seq += 1

    conn.commit()
    outcome = score_arm(conn, ledger, trace.trace_id, trace.order_id, turns)
    conn.close()
    after = world_mod.sha256_file(clone.path)

    if not world_mod.source_unchanged(clone):  # pragma: no cover - safety net
        raise RuntimeError(f"frozen world for {trace.trace_id} was mutated replaying a capture")

    arm = ArmRun(
        arm="candidate",
        trace_id=trace.trace_id,
        clone_path=str(clone.path),
        clone_sha256=clone.sha256,
        clone_sha256_after=after,
        source_world_sha256=clone.source_sha256,
        execution="re-executed",
        steps=replayed,
        ledger=ledger.rows,
        unsafe_effects=ledger.unsafe_effects,
        external_calls_executed=ledger.external_calls_executed,
        outcome="escalated" if outcome.escalated else "resolved",
        turns=turns,
    )
    return arm, outcome
