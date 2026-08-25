"""Tool execution under replay.

Three rules, enforced here and nowhere else:

1. Reads and internal writes happen against the *clone*, never a live system.
2. Effects that would leave our boundary (money movement, customer email) are
   never performed. They are recorded as SHADOWED and their intended outcome is
   reflected in the clone so the trajectory can continue realistically.
3. A tool the registry does not know about aborts the run. We cannot bound its
   blast radius, so we refuse rather than guess. This is the fail-closed rule.

There is no client, socket, or credential for any external system anywhere in
this package — the absence is the guarantee, the ledger is the evidence.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from apps.api import tool_registry
from apps.api.replay.ledger import Ledger, UnknownEffectError


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")


class ToolHost:
    """Executes the refund agent's tool surface against one cloned world."""

    def __init__(self, conn: sqlite3.Connection, ledger: Ledger, meta: dict[str, str]):
        self.conn = conn
        self.ledger = ledger
        self.now = _parse(meta.get("now", "2026-08-20T00:00:00Z"))
        self.sla_hours = int(meta.get("sla_hours", 48))
        self.aborted = False

    # ------------------------------------------------------------------ dispatch

    def call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if not tool_registry.is_known(tool_name):
            self.ledger.record(
                tool=tool_name,
                effect_class="unknown",
                target=str(args.get("order_id") or args.get("customer_id") or "?"),
                args=args,
                disposition="BLOCKED_UNKNOWN_EFFECT",
                note="Unregistered tool: blast radius undeclared, so the run is aborted.",
            )
            self.aborted = True
            raise UnknownEffectError(
                f"{tool_name!r} is not in the effect registry; refusing to execute it under replay."
            )
        handler = getattr(self, f"_t_{tool_name}")
        return handler(args)

    # ------------------------------------------------------------------ reads

    def _t_order_lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        oid = args.get("order_id", "")
        row = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (oid,)).fetchone()
        self.ledger.record(
            tool="order_lookup",
            effect_class="read",
            target=oid,
            args=args,
            disposition="READ_FROM_CLONE",
        )
        if row is None:
            return {"found": False, "order_id": oid}
        return {
            "found": True,
            "order_id": row["order_id"],
            "customer_id": row["customer_id"],
            "amount_cents": row["amount_cents"],
            "currency": row["currency"],
            "placed_at": row["placed_at"],
            "status": row["status"],
        }

    def _t_refund_status(self, args: dict[str, Any]) -> dict[str, Any]:
        oid = args.get("order_id", "")
        row = self.conn.execute(
            "SELECT * FROM refunds WHERE order_id = ? ORDER BY requested_at DESC LIMIT 1", (oid,)
        ).fetchone()
        self.ledger.record(
            tool="refund_status",
            effect_class="read",
            target=oid,
            args=args,
            disposition="READ_FROM_CLONE",
        )
        if row is None:
            return {"order_id": oid, "state": "none", "sla_hours": self.sla_hours}
        elapsed = (self.now - _parse(row["requested_at"])).total_seconds() / 3600.0
        return {
            "order_id": oid,
            "refund_id": row["refund_id"],
            "state": row["state"],
            "amount_cents": row["amount_cents"],
            "requested_at": row["requested_at"],
            "completed_at": row["completed_at"],
            "processor_ref": row["processor_ref"],
            "hours_since_request": round(elapsed, 1),
            "sla_hours": self.sla_hours,
            "sla_breached": elapsed > self.sla_hours,
        }

    # ------------------------------------------------------------------ external

    def _t_refund_execute(self, args: dict[str, Any]) -> dict[str, Any]:
        oid = args.get("order_id", "")
        amount = int(args.get("amount_cents") or 0)
        prior = self.conn.execute(
            "SELECT refund_id, state FROM refunds WHERE order_id = ?", (oid,)
        ).fetchall()
        note = "Payment-processor call suppressed; outcome simulated on the clone."
        if prior:
            note += f" Order already had {len(prior)} refund record(s): " + ", ".join(
                f"{r['refund_id']}={r['state']}" for r in prior
            )
        self.ledger.record(
            tool="refund_execute",
            effect_class="external",
            target=oid,
            args=args,
            disposition="SHADOWED",
            note=note,
        )
        rid = f"rf_sim_{uuid.uuid5(uuid.NAMESPACE_OID, f'{oid}:{len(prior)}').hex[:8]}"
        self.conn.execute(
            "INSERT INTO refunds(refund_id, order_id, amount_cents, state, requested_at, "
            "completed_at, processor_ref) VALUES (?,?,?,?,?,?,?)",
            (
                rid,
                oid,
                amount,
                "completed",
                self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"sim_{rid}",
            ),
        )
        return {"refund_id": rid, "order_id": oid, "state": "completed", "simulated": True}

    def _t_send_email(self, args: dict[str, Any]) -> dict[str, Any]:
        cid = args.get("customer_id", "")
        oid = args.get("order_id", "")
        template = args.get("template", "refund_confirmation")
        key = args.get("idempotency_key")
        existing = None
        if key:
            existing = self.conn.execute(
                "SELECT * FROM emails WHERE idempotency_key = ?", (key,)
            ).fetchone()
        self.ledger.record(
            tool="send_email",
            effect_class="external",
            target=cid,
            args=args,
            disposition="SHADOWED",
            note=(
                "Delivery suppressed; deduplicated on the supplied idempotency key."
                if existing
                else "Delivery suppressed; recorded on the clone only."
            ),
        )
        if existing:
            return {"email_id": existing["email_id"], "delivered": True, "deduplicated": True}
        eid = f"em_sim_{uuid.uuid5(uuid.NAMESPACE_OID, f'{oid}:{template}:{cid}:{self.conn.total_changes}').hex[:8]}"
        self.conn.execute(
            "INSERT INTO emails(email_id, order_id, customer_id, template, sent_at, idempotency_key) "
            "VALUES (?,?,?,?,?,?)",
            (eid, oid, cid, template, self.now.strftime("%Y-%m-%dT%H:%M:%SZ"), key),
        )
        return {"email_id": eid, "delivered": True, "deduplicated": False, "simulated": True}

    # ------------------------------------------------------------------ internal write

    def _t_escalate_to_human(self, args: dict[str, Any]) -> dict[str, Any]:
        oid = args.get("order_id", "")
        reason = args.get("reason", "")
        refund = self.conn.execute(
            "SELECT state FROM refunds WHERE order_id = ? ORDER BY requested_at DESC LIMIT 1", (oid,)
        ).fetchone()
        state = refund["state"] if refund else "none"
        self.ledger.record(
            tool="escalate_to_human",
            effect_class="shadow_write",
            target=oid,
            args=args,
            disposition="APPLIED_TO_CLONE",
            note="Support escalation written to the clone only.",
        )
        cust = self.conn.execute(
            "SELECT customer_id FROM orders WHERE order_id = ?", (oid,)
        ).fetchone()
        esc = f"esc_sim_{uuid.uuid5(uuid.NAMESPACE_OID, oid).hex[:8]}"
        self.conn.execute(
            "INSERT OR REPLACE INTO escalations(escalation_id, order_id, customer_id, reason, "
            "created_at, refund_state_at_escalation) VALUES (?,?,?,?,?,?)",
            (
                esc,
                oid,
                cust["customer_id"] if cust else "",
                reason,
                self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                state,
            ),
        )
        return {"escalation_id": esc, "created": True, "refund_state": state}
