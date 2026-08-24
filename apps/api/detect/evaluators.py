"""Deterministic failure evaluators.

These encode two failure modes an on-call engineer would have written a rule for
after seeing them once. They are precise and produce citable evidence, which is
what makes them useful in an investigation.

They are also incomplete on purpose. A third seeded failure family has no rule
here at all — finding it is left entirely to the generic anomaly model, so the
demo can show what happens for a failure nobody thought to write a rule for.
"""
from __future__ import annotations

from collections import defaultdict

from apps.api.contracts import EvidenceHit, TraceDetail
from apps.api.detect.features import TraceFeatures


def double_refund(trace: TraceDetail, f: TraceFeatures) -> EvidenceHit | None:
    """A refund issued on an order that already had one."""
    prior_state: dict[str, str] = {}
    executed: dict[str, int] = defaultdict(int)
    for ev in trace.events:
        if ev.type == "tool_result" and ev.tool_name == "refund_status":
            r = ev.result or {}
            oid = str(r.get("order_id") or trace.order_id)
            state = str(r.get("state", "none"))
            if state in ("completed", "processing"):
                prior_state[oid] = state
        elif ev.type == "tool_call" and ev.tool_name == "refund_execute":
            oid = str((ev.args or {}).get("order_id") or trace.order_id)
            executed[oid] += 1
            if oid in prior_state:
                return EvidenceHit(
                    source="evaluator",
                    rule_id="double_refund",
                    label="Refund issued on an already-refunded order",
                    detail=(
                        f"refund_execute called on {oid} at event {ev.seq} after refund_status "
                        f"reported state={prior_state[oid]}."
                    ),
                )
    for oid, n in executed.items():
        if n > 1:
            return EvidenceHit(
                source="evaluator",
                rule_id="double_refund",
                label="Refund executed more than once",
                detail=f"refund_execute called {n} times on {oid} within one trace.",
            )
    return None


def duplicate_confirmation(trace: TraceDetail, f: TraceFeatures) -> EvidenceHit | None:
    """The same confirmation email sent twice because a retry was not idempotent."""
    sends: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for ev in trace.events:
        if ev.type == "tool_call" and ev.tool_name == "send_email":
            a = ev.args or {}
            sends[(str(a.get("order_id", "")), str(a.get("template", "")))].append(a)
    for (oid, template), attempts in sends.items():
        if len(attempts) < 2:
            continue
        keys = {a.get("idempotency_key") for a in attempts}
        if len(keys) == 1 and None not in keys:
            continue  # retried safely under one key
        return EvidenceHit(
            source="evaluator",
            rule_id="duplicate_confirmation",
            label="Duplicate customer email",
            detail=(
                f"send_email called {len(attempts)}× for {oid}/{template} with "
                f"{'no idempotency key' if keys == {None} else 'differing idempotency keys'}; "
                f"{f.numeric.get('n_timeouts', 0):.0f} timeout(s) in this trace."
            ),
        )
    return None


RULES = [double_refund, duplicate_confirmation]


def evaluate(trace: TraceDetail, f: TraceFeatures) -> list[EvidenceHit]:
    return [hit for rule in RULES if (hit := rule(trace, f)) is not None]
