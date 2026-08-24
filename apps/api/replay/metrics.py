"""Outcome measurement.

Both arms are measured by exactly the same function reading exactly the same
kind of artifact: the final state of that arm's clone, plus its Effect Ledger.
Nothing is read from the agent's narration, and nothing is read from the
original recording — otherwise the two arms would not be comparable.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime

from apps.api.contracts import ArmMetrics
from apps.api.replay.ledger import Ledger


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")


@dataclass
class TraceOutcome:
    trace_id: str
    double_refund: bool
    duplicate_confirmation: bool
    premature_escalation: bool
    escalated: bool
    turns: int
    unsafe_effects: int
    external_calls_executed: int

    @property
    def passed(self) -> bool:
        return not (
            self.double_refund
            or self.duplicate_confirmation
            or self.premature_escalation
            or self.unsafe_effects
        )

    def failure_labels(self) -> list[str]:
        out = []
        if self.double_refund:
            out.append("double_refund")
        if self.duplicate_confirmation:
            out.append("duplicate_confirmation")
        if self.premature_escalation:
            out.append("premature_escalation")
        if self.unsafe_effects:
            out.append("unsafe_effect")
        return out

    def as_dict(self) -> dict:
        return {**asdict(self), "passed": self.passed, "failures": self.failure_labels()}


def score_arm(
    conn: sqlite3.Connection,
    ledger: Ledger,
    trace_id: str,
    order_id: str,
    turns: int,
) -> TraceOutcome:
    refunds = conn.execute(
        "SELECT refund_id, state, requested_at FROM refunds WHERE order_id = ?", (order_id,)
    ).fetchall()
    settled = [r for r in refunds if r["state"] in ("completed", "processing")]

    confirmations = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE order_id = ? AND template = 'refund_confirmation'",
        (order_id,),
    ).fetchone()[0]

    esc = conn.execute(
        "SELECT * FROM escalations WHERE order_id = ? LIMIT 1", (order_id,)
    ).fetchone()

    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM world_meta")}
    now = _parse(meta.get("now", "2026-08-20T00:00:00Z"))
    sla_hours = int(meta.get("sla_hours", 48))

    premature = False
    if esc is not None:
        # An escalation is avoidable unless the SLA was actually breached or the
        # refund genuinely failed. Frustration alone is not a breach.
        state = esc["refund_state_at_escalation"]
        breached = False
        if refunds:
            newest = max(refunds, key=lambda r: r["requested_at"])
            breached = (now - _parse(newest["requested_at"])).total_seconds() / 3600.0 > sla_hours
        premature = not (breached or state == "failed")

    return TraceOutcome(
        trace_id=trace_id,
        double_refund=len(settled) > 1,
        duplicate_confirmation=confirmations > 1,
        premature_escalation=premature,
        escalated=esc is not None,
        turns=turns,
        unsafe_effects=ledger.unsafe_effects,
        external_calls_executed=ledger.external_calls_executed,
    )


def aggregate(outcomes: list[TraceOutcome]) -> ArmMetrics:
    n = max(len(outcomes), 1)
    return ArmMetrics(
        double_refund_rate=round(sum(o.double_refund for o in outcomes) / n, 4),
        duplicate_confirmation_rate=round(sum(o.duplicate_confirmation for o in outcomes) / n, 4),
        premature_escalation_rate=round(sum(o.premature_escalation for o in outcomes) / n, 4),
        resolution_rate=round(sum(not o.escalated for o in outcomes) / n, 4),
        avg_turns=round(sum(o.turns for o in outcomes) / n, 2),
        unsafe_effects=sum(o.unsafe_effects for o in outcomes),
        external_calls_executed=sum(o.external_calls_executed for o in outcomes),
    )
