"""Deterministic synthetic-corpus generator for the refund-support demo.

Produces, given a fixed seed, a fully reproducible set of:
  - traces + events              (var/traces.db)
  - one frozen world per trace   (var/worlds/<trace_id>.sqlite)
  - the offline family labels    (var/hidden_labels.db)   -- scripts/ only
  - the v1 agent config          (var/configs.db)

No wall-clock, no UUIDs, no dict/set iteration nondeterminism: every random
choice is drawn from a single `random.Random(SEED)` instance consumed in a
fixed order. See SCHEMA.md for the authoritative table definitions.

CRITICAL: nothing generated here may encode which family a trace belongs to.
The family is only inferable from the *structure* of events + world state.
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apps.api import paths

SEED = 1337
SLA_HOURS = 48

WORLD_START = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
WORLD_END = datetime(2026, 8, 20, 23, 59, 59, tzinfo=timezone.utc)

INTENTS = ["refund_request", "refund_status_inquiry", "order_question", "cancel_request"]
OUTCOMES = ["resolved", "escalated", "abandoned"]

FAMILY_F1 = "F1_double_refund"
FAMILY_F2 = "F2_duplicate_confirmation"
FAMILY_F3 = "F3_premature_escalation"
FAMILY_HEALTHY = "healthy"

# ---------------------------------------------------------------------------
# time / id helpers
# ---------------------------------------------------------------------------


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def random_now(rng) -> datetime:
    span = int((WORLD_END - WORLD_START).total_seconds())
    off = rng.randrange(0, span + 1)
    return WORLD_START + timedelta(seconds=off)


def rand_hex(rng, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


@dataclass
class Ids:
    customer_n: int = 100
    main_order_n: int = 10000
    unrelated_order_n: int = 50000
    refund_n: int = 1
    email_n: int = 1
    escalation_n: int = 1

    def new_customer(self) -> str:
        v = self.customer_n
        self.customer_n += 1
        return f"cus_{v:04d}"

    def new_order(self, *, main: bool) -> str:
        if main:
            v = self.main_order_n
            self.main_order_n += 1
        else:
            v = self.unrelated_order_n
            self.unrelated_order_n += 1
        return f"ord_{v:05d}"

    def new_refund(self) -> str:
        v = self.refund_n
        self.refund_n += 1
        return f"rfd_{v:06d}"

    def new_email(self) -> str:
        v = self.email_n
        self.email_n += 1
        return f"eml_{v:06d}"

    def new_escalation(self) -> str:
        v = self.escalation_n
        self.escalation_n += 1
        return f"esc_{v:06d}"


@dataclass
class Ctx:
    rng: Any
    ids: Ids = field(default_factory=Ids)


# ---------------------------------------------------------------------------
# config (v1)
# ---------------------------------------------------------------------------


def config_hash(model: str, system_prompt: str, tools: list) -> str:
    payload = json.dumps(
        {"model": model, "system_prompt": system_prompt, "tools": tools},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


V1_MODEL = "claude-opus-5"

V1_SYSTEM_PROMPT = (
    "You are a customer support agent for an online retailer. Customers write "
    "in about problems with orders they've already placed, and a large share of "
    "these conversations are about refunds. Your overall job is to resolve the "
    "customer's refund concern and make sure they receive their money as "
    "quickly as possible. Use the tools available to you to look up the "
    "customer's order, look into their refund, and take whatever action is "
    "needed to get the situation sorted out. Don't leave a refund request "
    "half-finished — if there is more you can do to get the customer paid, go "
    "ahead and do it rather than just describing the situation back to them. "
    "Keep the customer updated by email when it makes sense, and let them know "
    "once things have been taken care of. If a customer seems frustrated, "
    "upset, or like they've been waiting too long, escalate the conversation "
    "to a human teammate so a person can step in and take over from there. Be "
    "warm, clear, and concise in every message, and never ask the customer for "
    "information you can already pull up yourself. Your goal at the end of "
    "every conversation is for the customer to feel confident that their money "
    "is on its way and that their problem has genuinely been solved, not just "
    "acknowledged."
)

V1_TOOLS = [
    {
        "name": "order_lookup",
        "description": "Look up an order by its order ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to look up."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "refund_status",
        "description": "Check and process the refund status for an order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to check."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "refund_execute",
        "description": "Execute a refund for an order for a given amount.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to refund."},
                "amount_cents": {"type": "integer", "description": "Refund amount in cents."},
            },
            "required": ["order_id", "amount_cents"],
        },
    },
    {
        "name": "send_email",
        "description": "Send a templated email to the customer about their order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "The customer to email."},
                "template": {
                    "type": "string",
                    "enum": ["refund_confirmation", "refund_delay_notice"],
                    "description": "Which email template to send.",
                },
                "order_id": {"type": "string", "description": "The order the email relates to."},
            },
            "required": ["customer_id", "template", "order_id"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate the conversation to a human support agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order the escalation relates to."},
                "reason": {"type": "string", "description": "Why the conversation is being escalated."},
            },
            "required": ["order_id", "reason"],
        },
    },
]


def build_v1_config(created_at: str = "2026-06-01T00:00:00Z") -> dict[str, Any]:
    h = config_hash(V1_MODEL, V1_SYSTEM_PROMPT, V1_TOOLS)
    return {
        "version": "v1",
        "created_at": created_at,
        "model": V1_MODEL,
        "system_prompt": V1_SYSTEM_PROMPT,
        "tools": V1_TOOLS,
        "config_hash": h,
        "status": "active",
        "parent_version": None,
        "notes": "Baseline v1 configuration seeded by scripts/seed.py.",
    }


# ---------------------------------------------------------------------------
# neutral text pools (no family-identifying wording anywhere)
# ---------------------------------------------------------------------------

USER_MSGS = {
    "refund_status_inquiry": [
        "Hi, can you tell me the status of my refund for {order_id}?",
        "Just checking in on my refund for order {order_id} - any update?",
        "Where's my refund for {order_id}? It's been a few days.",
        "Can you check on the refund for {order_id}, please?",
        "I'm following up on a refund for order {order_id}.",
    ],
    "refund_request": [
        "I'd like to request a refund for order {order_id}.",
        "Can you refund my order {order_id}? It wasn't what I expected.",
        "I want my money back for {order_id}, please process a refund.",
        "Please refund {order_id}, I no longer need it.",
        "Can you start a refund on order {order_id}?",
    ],
    "order_question": [
        "Hi, when is order {order_id} supposed to arrive?",
        "Can you tell me the status of order {order_id}?",
        "I have a question about my order {order_id}.",
        "What's happening with order {order_id}?",
        "Can you give me an update on order {order_id}?",
    ],
    "cancel_request": [
        "I need to cancel order {order_id}.",
        "Can you cancel {order_id} for me?",
        "Please cancel my order {order_id} before it ships.",
        "I'd like to cancel order {order_id}, is that possible?",
        "Can you stop order {order_id} from shipping?",
    ],
}

FOLLOWUP_STATUS_MSGS = [
    "It's still not showing up on my end, can you check again?",
    "Any update since we last looked?",
    "Can you take another look, please?",
]

MODEL_THINK = [
    "Let me look into that for you.",
    "One moment while I check the order details.",
    "I'll pull up the order now.",
    "Checking on that right away.",
    "Let me take a look at this for you.",
    "I'm reviewing the order information now.",
    "Give me a moment to check.",
    "Let me see what's going on here.",
]

AGENT_CLOSERS_RESOLVED = [
    "Your refund has been processed and should reflect in a few business days.",
    "Thanks for your patience - this has been taken care of.",
    "You're all set. Let us know if you need anything else.",
    "I've confirmed the details and sent you a confirmation email.",
    "That's been handled on our end - you should be all set.",
]

STATUS_INFO_CLOSERS = [
    "Your refund is still being processed - thanks for your patience.",
    "I don't see a refund on file for this order yet. Let me know if you'd like to start one.",
    "Here's the latest on your refund - let me know if you have more questions.",
    "Your refund shows as completed on our end already.",
]

ORDER_INFO_CLOSERS = [
    "Your order is on track and should arrive soon.",
    "Here's the latest status on your order - let me know if you have more questions.",
    "Everything looks on schedule for your order.",
]

CANCEL_CLOSERS = [
    "Your order has been cancelled as requested.",
    "I've noted your cancellation request; our team will confirm shortly.",
    "That order is set to be cancelled.",
]

ABANDONED_CLOSERS = [
    "We didn't hear back further, so I'll close this conversation for now - reach out anytime.",
    "Since we haven't heard back, I'll go ahead and close this out. Feel free to reopen if needed.",
]

ESCALATE_REASONS_UNHAPPY = [
    "Customer is unhappy about the wait and asked to speak with a person.",
    "Customer sounds frustrated with the delay and requested escalation.",
    "Customer wants a human to take over this conversation.",
]

JUSTIFIED_REASONS = [
    "This refund has been processing longer than our standard window; escalating for manual review.",
    "Refund processing has run past our usual timeframe, so I'm looping in a specialist.",
    "This refund is taking longer than expected even after a delay notice; escalating for follow-up.",
]

ESCALATION_HANDOFF = [
    "I'm connecting you with a member of our support team who can help further.",
    "I've looped in a colleague who will pick this up from here.",
    "A specialist on our team will follow up with you shortly.",
]

SUMMARY_TEMPLATES = {
    "refund_status_inquiry": "Customer asked about refund status for {order_id}.",
    "refund_request": "Customer requested a refund for {order_id}.",
    "order_question": "Customer asked a question about order {order_id}.",
    "cancel_request": "Customer asked to cancel order {order_id}.",
}


def make_summary(intent: str, order_id: str, outcome: str) -> str:
    base = SUMMARY_TEMPLATES[intent].format(order_id=order_id)
    if outcome == "escalated":
        return base + " Escalated to a human agent."
    if outcome == "abandoned":
        return base + " Customer did not respond further."
    return base + " Resolved by the agent."


BANNED_SUBSTRINGS = [
    "duplicate",
    "premature",
    "erroneous",
    "double",
    "f1_double_refund",
    "f2_duplicate_confirmation",
    "f3_premature_escalation",
    "hidden_label",
    "family",
]


# ---------------------------------------------------------------------------
# event log
# ---------------------------------------------------------------------------


class EventLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._seq = 0

    def add(
        self,
        type_: str,
        *,
        tool_name: str | None = None,
        args: dict | None = None,
        result: dict | None = None,
        latency: int = 0,
        error: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        ev = {
            "seq": self._seq,
            "type": type_,
            "tool_name": tool_name,
            "args_json": json.dumps(args, sort_keys=True) if args is not None else None,
            "result_json": json.dumps(result, sort_keys=True) if result is not None else None,
            "latency_ms": int(latency),
            "error": error,
            "content": content,
        }
        self._seq += 1
        self.events.append(ev)
        return ev

    def turns(self) -> int:
        return sum(1 for e in self.events if e["type"] == "model_turn")


def finalize_duration(rng, events: list[dict], target_ms: tuple[int, int] | None = None) -> int:
    sum_latency = sum(e["latency_ms"] for e in events)
    gaps = max(len(events) - 1, 1)
    if target_ms is None:
        gap_total = sum(rng.randint(20, 150) for _ in range(gaps))
        return sum_latency + gap_total
    lo, hi = target_ms
    target = rng.randint(lo, hi)
    return max(target, sum_latency + gaps * 10)


def do_tool(log: EventLog, ctx: Ctx, tool_name: str, args: dict, result: dict, latency: int, error: str | None = None) -> None:
    log.add("model_turn", content=ctx.rng.choice(MODEL_THINK), latency=ctx.rng.randint(600, 2500))
    log.add("tool_call", tool_name=tool_name, args=args, latency=0)
    log.add("tool_result", tool_name=tool_name, result=result, latency=latency, error=error)


# ---------------------------------------------------------------------------
# world / order / refund builders
# ---------------------------------------------------------------------------


def make_order_row(ctx: Ctx, customer_id: str, now_dt: datetime, *, main: bool, status: str | None = None, amount_cents: int | None = None) -> dict[str, Any]:
    oid = ctx.ids.new_order(main=main)
    if amount_cents is None:
        amount_cents = ctx.rng.randrange(1500, 45001, 100)
    if status is None:
        status = ctx.rng.choices(["delivered", "shipped", "cancelled"], weights=[70, 20, 10])[0]
    placed_at = now_dt - timedelta(days=ctx.rng.uniform(10, 90))
    return {
        "order_id": oid,
        "customer_id": customer_id,
        "amount_cents": amount_cents,
        "currency": "USD",
        "placed_at": iso(placed_at),
        "status": status,
    }


def make_customer_and_orders(ctx: Ctx, now_dt: datetime, *, main_status: str | None = None, main_amount: int | None = None) -> tuple[str, dict, list[dict]]:
    customer_id = ctx.ids.new_customer()
    main_order = make_order_row(ctx, customer_id, now_dt, main=True, status=main_status, amount_cents=main_amount)
    n_unrelated = ctx.rng.randint(1, 3)
    unrelated = [make_order_row(ctx, customer_id, now_dt, main=False) for _ in range(n_unrelated)]
    return customer_id, main_order, unrelated


def make_world(trace_id: str, now_dt: datetime, main_order: dict, unrelated_orders: list[dict], refunds: list[dict] | None = None) -> dict[str, Any]:
    return {
        "orders": [main_order] + unrelated_orders,
        "refunds": refunds or [],
        "emails": [],
        "escalations": [],
        "meta": {
            "trace_id": trace_id,
            "frozen_at": iso(now_dt),
            "sla_hours": str(SLA_HOURS),
            "now": iso(now_dt),
        },
    }


# ---------------------------------------------------------------------------
# tool-call helpers (produce trace-consistent args/results)
# ---------------------------------------------------------------------------


def order_lookup_call(log: EventLog, ctx: Ctx, order_row: dict) -> None:
    result = {
        "found": True,
        "order_id": order_row["order_id"],
        "customer_id": order_row["customer_id"],
        "amount_cents": order_row["amount_cents"],
        "currency": order_row["currency"],
        "placed_at": order_row["placed_at"],
        "status": order_row["status"],
    }
    do_tool(log, ctx, "order_lookup", {"order_id": order_row["order_id"]}, result, ctx.rng.randint(40, 300))


def refund_status_call(log: EventLog, ctx: Ctx, order_id: str, refund_row: dict | None, now_dt: datetime) -> None:
    if refund_row is None:
        result = {"order_id": order_id, "state": "none", "sla_hours": SLA_HOURS}
    else:
        elapsed = (now_dt - parse_iso(refund_row["requested_at"])).total_seconds() / 3600.0
        result = {
            "order_id": order_id,
            "refund_id": refund_row["refund_id"],
            "state": refund_row["state"],
            "amount_cents": refund_row["amount_cents"],
            "requested_at": refund_row["requested_at"],
            "completed_at": refund_row["completed_at"],
            "processor_ref": refund_row["processor_ref"],
            "hours_since_request": round(elapsed, 1),
            "sla_hours": SLA_HOURS,
            "sla_breached": elapsed > SLA_HOURS,
        }
    do_tool(log, ctx, "refund_status", {"order_id": order_id}, result, ctx.rng.randint(40, 300))


def refund_execute_call(log: EventLog, ctx: Ctx, order_id: str, amount_cents: int, now_dt: datetime) -> dict[str, Any]:
    rid = ctx.ids.new_refund()
    ref = "prc_" + rand_hex(ctx.rng, 10)
    result = {
        "refund_id": rid,
        "order_id": order_id,
        "amount_cents": amount_cents,
        "state": "completed",
        "requested_at": iso(now_dt),
        "completed_at": iso(now_dt),
        "processor_ref": ref,
    }
    do_tool(log, ctx, "refund_execute", {"order_id": order_id, "amount_cents": amount_cents}, result, ctx.rng.randint(400, 1500))
    return result


def send_email_call(
    log: EventLog,
    ctx: Ctx,
    customer_id: str,
    order_id: str,
    template: str,
    now_dt: datetime,
    *,
    idempotency_key: str | None = None,
    reuse_email_id: str | None = None,
) -> str:
    eid = reuse_email_id or ctx.ids.new_email()
    args = {"customer_id": customer_id, "order_id": order_id, "template": template}
    if idempotency_key:
        args["idempotency_key"] = idempotency_key
    result = {
        "email_id": eid,
        "order_id": order_id,
        "customer_id": customer_id,
        "template": template,
        "delivered": True,
        "sent_at": iso(now_dt),
    }
    do_tool(log, ctx, "send_email", args, result, ctx.rng.randint(200, 900))
    return eid


def send_email_timeout_call(
    log: EventLog,
    ctx: Ctx,
    customer_id: str,
    order_id: str,
    template: str,
    now_dt: datetime,
    *,
    idempotency_key: str | None = None,
) -> str:
    eid = ctx.ids.new_email()
    args = {"customer_id": customer_id, "order_id": order_id, "template": template}
    if idempotency_key:
        args["idempotency_key"] = idempotency_key
    result = {
        "email_id": eid,
        "order_id": order_id,
        "customer_id": customer_id,
        "template": template,
        "delivered": True,
        "sent_at": iso(now_dt),
    }
    do_tool(log, ctx, "send_email", args, result, ctx.rng.randint(8000, 15000), error="timeout")
    return eid


def escalate_call(log: EventLog, ctx: Ctx, order_id: str, reason: str, refund_state: str, now_dt: datetime) -> None:
    xid = ctx.ids.new_escalation()
    result = {
        "escalation_id": xid,
        "order_id": order_id,
        "status": "queued",
        "refund_state_at_escalation": refund_state,
    }
    do_tool(log, ctx, "escalate_to_human", {"order_id": order_id, "reason": reason}, result, ctx.rng.randint(50, 300))


# ---------------------------------------------------------------------------
# scenario builders -- each returns (trace_fields, events, world)
# ---------------------------------------------------------------------------


def _f1(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = "refund_status_inquiry"
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
    oid = main_order["order_id"]
    amt = main_order["amount_cents"]

    requested_at = now_dt - timedelta(days=ctx.rng.uniform(3, 10))
    completed_at = requested_at + timedelta(hours=ctx.rng.uniform(6, 48))
    pre_refund = {
        "refund_id": ctx.ids.new_refund(),
        "order_id": oid,
        "amount_cents": amt,
        "state": "completed",
        "requested_at": iso(requested_at),
        "completed_at": iso(completed_at),
        "processor_ref": "prc_" + rand_hex(ctx.rng, 10),
    }

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)
    refund_status_call(log, ctx, oid, pre_refund, now_dt)
    refund_execute_call(log, ctx, oid, amt, now_dt)
    send_email_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt)
    log.add("agent_msg", content=ctx.rng.choice(AGENT_CLOSERS_RESOLVED), latency=ctx.rng.randint(400, 1200))

    duration = finalize_duration(ctx.rng, log.events)
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "resolved",
        "summary": make_summary(intent, oid, "resolved"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=[pre_refund])
    return trace, log.events, world


def _f2(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = "refund_request"
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
    oid = main_order["order_id"]
    amt = main_order["amount_cents"]

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)
    refund_execute_call(log, ctx, oid, amt, now_dt)
    # first send times out; the agent cannot tell whether it landed, retries
    # without any idempotency key -> a second, distinct email is generated.
    send_email_timeout_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt)
    send_email_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt)
    log.add("agent_msg", content=ctx.rng.choice(AGENT_CLOSERS_RESOLVED), latency=ctx.rng.randint(400, 1200))

    duration = finalize_duration(ctx.rng, log.events)
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "resolved",
        "summary": make_summary(intent, oid, "resolved"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=[])
    return trace, log.events, world


def _f3(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = "refund_status_inquiry"
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
    oid = main_order["order_id"]

    requested_at = now_dt - timedelta(hours=ctx.rng.uniform(18, 40))
    refund = {
        "refund_id": ctx.ids.new_refund(),
        "order_id": oid,
        "amount_cents": main_order["amount_cents"],
        "state": "processing",
        "requested_at": iso(requested_at),
        "completed_at": None,
        "processor_ref": None,
    }

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)
    refund_status_call(log, ctx, oid, refund, now_dt)
    if ctx.rng.random() < 0.5:
        log.add("model_turn", content=ctx.rng.choice(MODEL_THINK), latency=ctx.rng.randint(600, 2500))
    reason = ctx.rng.choice(ESCALATE_REASONS_UNHAPPY)
    escalate_call(log, ctx, oid, reason, "processing", now_dt)
    log.add("escalation", content=ctx.rng.choice(ESCALATION_HANDOFF), latency=ctx.rng.randint(100, 400))

    duration = finalize_duration(ctx.rng, log.events, target_ms=(15000, 40000))
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "escalated",
        "summary": make_summary(intent, oid, "escalated"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=[refund])
    return trace, log.events, world


def _healthy_justified_escalation(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = "refund_status_inquiry"
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
    oid = main_order["order_id"]

    requested_at = now_dt - timedelta(hours=ctx.rng.uniform(55, 90))
    refund = {
        "refund_id": ctx.ids.new_refund(),
        "order_id": oid,
        "amount_cents": main_order["amount_cents"],
        "state": "processing",
        "requested_at": iso(requested_at),
        "completed_at": None,
        "processor_ref": None,
    }

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)
    refund_status_call(log, ctx, oid, refund, now_dt)
    log.add("model_turn", content=ctx.rng.choice(MODEL_THINK), latency=ctx.rng.randint(600, 2500))
    if ctx.rng.random() < 0.5:
        log.add("user_msg", content=ctx.rng.choice(FOLLOWUP_STATUS_MSGS))
        log.add("model_turn", content=ctx.rng.choice(MODEL_THINK), latency=ctx.rng.randint(600, 2500))
    send_email_call(log, ctx, customer_id, oid, "refund_delay_notice", now_dt)
    reason = ctx.rng.choice(JUSTIFIED_REASONS)
    escalate_call(log, ctx, oid, reason, "processing", now_dt)
    log.add("escalation", content=ctx.rng.choice(ESCALATION_HANDOFF), latency=ctx.rng.randint(100, 400))

    duration = finalize_duration(ctx.rng, log.events)
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "escalated",
        "summary": make_summary(intent, oid, "escalated"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=[refund])
    return trace, log.events, world


def _healthy_successful_retry(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = "refund_request"
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
    oid = main_order["order_id"]
    amt = main_order["amount_cents"]

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)
    refund_execute_call(log, ctx, oid, amt, now_dt)
    idem_key = "idem_" + rand_hex(ctx.rng, 16)
    first_id = send_email_timeout_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt, idempotency_key=idem_key)
    # retry reuses the same idempotency key -> deduplicated to the same email
    send_email_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt, idempotency_key=idem_key, reuse_email_id=first_id)
    log.add("agent_msg", content=ctx.rng.choice(AGENT_CLOSERS_RESOLVED), latency=ctx.rng.randint(400, 1200))

    duration = finalize_duration(ctx.rng, log.events)
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "resolved",
        "summary": make_summary(intent, oid, "resolved"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=[])
    return trace, log.events, world


def _healthy_repeat_status_check(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = "refund_status_inquiry"
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
    oid = main_order["order_id"]

    refund = None
    if ctx.rng.random() < 0.5:
        requested_at = now_dt - timedelta(hours=ctx.rng.uniform(2, 120))
        refund = {
            "refund_id": ctx.ids.new_refund(),
            "order_id": oid,
            "amount_cents": main_order["amount_cents"],
            "state": "processing",
            "requested_at": iso(requested_at),
            "completed_at": None,
            "processor_ref": None,
        }

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)
    refund_status_call(log, ctx, oid, refund, now_dt)
    n_checks = ctx.rng.randint(1, 2)  # additional checks beyond the first (total 2-3)
    for _ in range(n_checks):
        log.add("user_msg", content=ctx.rng.choice(FOLLOWUP_STATUS_MSGS))
        refund_status_call(log, ctx, oid, refund, now_dt)
    log.add("agent_msg", content=ctx.rng.choice(STATUS_INFO_CLOSERS), latency=ctx.rng.randint(400, 1200))

    duration = finalize_duration(ctx.rng, log.events)
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "resolved",
        "summary": make_summary(intent, oid, "resolved"),
    }
    refunds = [refund] if refund is not None else []
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=refunds)
    return trace, log.events, world


def _healthy_slow_resolved(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = ctx.rng.choice(["refund_request", "refund_status_inquiry", "order_question"])
    status = "delivered" if intent != "order_question" else None
    customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status=status)
    oid = main_order["order_id"]
    amt = main_order["amount_cents"]

    log = EventLog()
    log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
    order_lookup_call(log, ctx, main_order)

    # extra back-and-forth clarification before getting to the point
    n_extra = ctx.rng.randint(3, 6)
    for _ in range(n_extra):
        log.add("user_msg", content=ctx.rng.choice(FOLLOWUP_STATUS_MSGS))
        log.add("model_turn", content=ctx.rng.choice(MODEL_THINK), latency=ctx.rng.randint(600, 2500))

    if intent == "refund_request":
        refund_execute_call(log, ctx, oid, amt, now_dt)
        send_email_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt)
        closer = ctx.rng.choice(AGENT_CLOSERS_RESOLVED)
    elif intent == "refund_status_inquiry":
        refund_status_call(log, ctx, oid, None, now_dt)
        closer = ctx.rng.choice(STATUS_INFO_CLOSERS)
    else:
        closer = ctx.rng.choice(ORDER_INFO_CLOSERS)

    log.add("agent_msg", content=closer, latency=ctx.rng.randint(400, 1200))

    duration = finalize_duration(ctx.rng, log.events, target_ms=(60000, 150000))
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "resolved",
        "summary": make_summary(intent, oid, "resolved"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=[])
    return trace, log.events, world


def _healthy_ordinary(ctx: Ctx, trace_id: str, now_dt: datetime):
    intent = ctx.rng.choice(INTENTS)
    abandoned = ctx.rng.random() < 0.05

    if intent == "refund_request":
        customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
        oid = main_order["order_id"]
        amt = main_order["amount_cents"]
        log = EventLog()
        log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
        order_lookup_call(log, ctx, main_order)
        if not abandoned:
            if ctx.rng.random() < 0.3:
                refund_status_call(log, ctx, oid, None, now_dt)
            refund_execute_call(log, ctx, oid, amt, now_dt)
            send_email_call(log, ctx, customer_id, oid, "refund_confirmation", now_dt)
            closer = ctx.rng.choice(AGENT_CLOSERS_RESOLVED)
        else:
            closer = ctx.rng.choice(ABANDONED_CLOSERS)
        refunds = []

    elif intent == "refund_status_inquiry":
        customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="delivered")
        oid = main_order["order_id"]
        roll = ctx.rng.random()
        refund = None
        if roll < 0.3:
            requested_at = now_dt - timedelta(hours=ctx.rng.uniform(1, 200))
            refund = {
                "refund_id": ctx.ids.new_refund(),
                "order_id": oid,
                "amount_cents": main_order["amount_cents"],
                "state": "processing",
                "requested_at": iso(requested_at),
                "completed_at": None,
                "processor_ref": None,
            }
        elif roll < 0.6:
            requested_at = now_dt - timedelta(days=ctx.rng.uniform(1, 20))
            completed_at = requested_at + timedelta(hours=ctx.rng.uniform(2, 40))
            refund = {
                "refund_id": ctx.ids.new_refund(),
                "order_id": oid,
                "amount_cents": main_order["amount_cents"],
                "state": "completed",
                "requested_at": iso(requested_at),
                "completed_at": iso(completed_at),
                "processor_ref": "prc_" + rand_hex(ctx.rng, 10),
            }
        log = EventLog()
        log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
        order_lookup_call(log, ctx, main_order)
        if not abandoned:
            refund_status_call(log, ctx, oid, refund, now_dt)
            closer = ctx.rng.choice(STATUS_INFO_CLOSERS)
        else:
            closer = ctx.rng.choice(ABANDONED_CLOSERS)
        refunds = [refund] if refund is not None else []

    elif intent == "order_question":
        customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt)
        oid = main_order["order_id"]
        log = EventLog()
        log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
        order_lookup_call(log, ctx, main_order)
        closer = ctx.rng.choice(ORDER_INFO_CLOSERS) if not abandoned else ctx.rng.choice(ABANDONED_CLOSERS)
        refunds = []

    else:  # cancel_request
        customer_id, main_order, unrelated = make_customer_and_orders(ctx, now_dt, main_status="shipped")
        oid = main_order["order_id"]
        log = EventLog()
        log.add("user_msg", content=ctx.rng.choice(USER_MSGS[intent]).format(order_id=oid))
        order_lookup_call(log, ctx, main_order)
        closer = ctx.rng.choice(CANCEL_CLOSERS) if not abandoned else ctx.rng.choice(ABANDONED_CLOSERS)
        refunds = []

    log.add("agent_msg", content=closer, latency=ctx.rng.randint(400, 1200))

    duration = finalize_duration(ctx.rng, log.events)
    trace = {
        "customer_id": customer_id,
        "order_id": oid,
        "intent": intent,
        "duration_ms": duration,
        "turns": log.turns(),
        "outcome": "abandoned" if abandoned else "resolved",
        "summary": make_summary(intent, oid, "abandoned" if abandoned else "resolved"),
    }
    world = make_world(trace_id, now_dt, main_order, unrelated, refunds=refunds)
    return trace, log.events, world


_HEALTHY_SUBTYPE_BUILDERS = {
    "justified_escalation": _healthy_justified_escalation,
    "successful_retry": _healthy_successful_retry,
    "repeat_status_check": _healthy_repeat_status_check,
    "slow_resolved": _healthy_slow_resolved,
    "ordinary": _healthy_ordinary,
}

_FAMILY_BUILDERS = {
    FAMILY_F1: _f1,
    FAMILY_F2: _f2,
    FAMILY_F3: _f3,
}


def build_trace(ctx: Ctx, trace_id: str, family: str, subtype: str | None):
    now_dt = random_now(ctx.rng)
    if family == FAMILY_HEALTHY:
        builder = _HEALTHY_SUBTYPE_BUILDERS[subtype]
    else:
        builder = _FAMILY_BUILDERS[family]
    trace_fields, events, world = builder(ctx, trace_id, now_dt)
    trace_fields = dict(trace_fields)
    trace_fields["trace_id"] = trace_id
    trace_fields["ts"] = iso(now_dt)
    trace_fields["config_version"] = "v1"
    return trace_fields, events, world


# ---------------------------------------------------------------------------
# plan / orchestration
# ---------------------------------------------------------------------------


def build_plan() -> list[tuple[str, str | None]]:
    plan: list[tuple[str, str | None]] = []
    plan += [(FAMILY_F1, None)] * 80
    plan += [(FAMILY_F2, None)] * 70
    plan += [(FAMILY_F3, None)] * 70
    plan += [(FAMILY_HEALTHY, "justified_escalation")] * 60
    plan += [(FAMILY_HEALTHY, "successful_retry")] * 50
    plan += [(FAMILY_HEALTHY, "repeat_status_check")] * 45
    plan += [(FAMILY_HEALTHY, "slow_resolved")] * 40
    plan += [(FAMILY_HEALTHY, "ordinary")] * 585
    assert len(plan) == 1000
    return plan


def generate(seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    ctx = Ctx(rng=rng)

    plan = build_plan()
    rng.shuffle(plan)

    traces: list[dict[str, Any]] = []
    events_by_trace: dict[str, list[dict[str, Any]]] = {}
    worlds_by_trace: dict[str, dict[str, Any]] = {}
    labels: dict[str, str] = {}

    for i, (family, subtype) in enumerate(plan):
        trace_id = f"tr_{i + 1:06d}"
        trace_fields, events, world = build_trace(ctx, trace_id, family, subtype)
        traces.append(trace_fields)
        events_by_trace[trace_id] = events
        worlds_by_trace[trace_id] = world
        labels[trace_id] = family

    config = build_v1_config()

    return {
        "traces": traces,
        "events": events_by_trace,
        "worlds": worlds_by_trace,
        "labels": labels,
        "config": config,
    }


# ---------------------------------------------------------------------------
# DB writers
# ---------------------------------------------------------------------------

TRACES_SCHEMA = """
CREATE TABLE traces(
  trace_id       TEXT PRIMARY KEY,
  ts             TEXT NOT NULL,
  customer_id    TEXT NOT NULL,
  order_id       TEXT NOT NULL,
  intent         TEXT NOT NULL,
  config_version TEXT NOT NULL,
  duration_ms    INTEGER NOT NULL,
  turns          INTEGER NOT NULL,
  outcome        TEXT NOT NULL,
  summary        TEXT NOT NULL
);
CREATE TABLE events(
  trace_id   TEXT NOT NULL,
  seq        INTEGER NOT NULL,
  type       TEXT NOT NULL,
  tool_name  TEXT,
  args_json  TEXT,
  result_json TEXT,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  error      TEXT,
  content    TEXT,
  PRIMARY KEY(trace_id, seq)
);
CREATE INDEX idx_events_trace ON events(trace_id);
"""

WORLD_SCHEMA = """
CREATE TABLE orders(
  order_id TEXT PRIMARY KEY, customer_id TEXT, amount_cents INTEGER,
  currency TEXT, placed_at TEXT, status TEXT);
CREATE TABLE refunds(
  refund_id TEXT PRIMARY KEY, order_id TEXT, amount_cents INTEGER,
  state TEXT, requested_at TEXT, completed_at TEXT, processor_ref TEXT);
CREATE TABLE emails(
  email_id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT,
  template TEXT, sent_at TEXT, idempotency_key TEXT);
CREATE TABLE escalations(
  escalation_id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT,
  reason TEXT, created_at TEXT, refund_state_at_escalation TEXT);
CREATE TABLE world_meta(key TEXT PRIMARY KEY, value TEXT);
"""

HIDDEN_LABELS_SCHEMA = "CREATE TABLE hidden_labels(trace_id TEXT PRIMARY KEY, family TEXT);"

CONFIGS_SCHEMA = """
CREATE TABLE agent_configs(
  version TEXT PRIMARY KEY,
  created_at TEXT, model TEXT,
  system_prompt TEXT, tools_json TEXT,
  config_hash TEXT,
  status TEXT,
  parent_version TEXT, notes TEXT
);
"""


def _open(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.isolation_level = None
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    return conn


def write_traces_db(path: Path, traces: list[dict[str, Any]], events_by_trace: dict[str, list[dict[str, Any]]]) -> None:
    conn = _open(path)
    conn.executescript(TRACES_SCHEMA)
    conn.execute("BEGIN")
    conn.executemany(
        "INSERT INTO traces(trace_id, ts, customer_id, order_id, intent, config_version, "
        "duration_ms, turns, outcome, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                t["trace_id"], t["ts"], t["customer_id"], t["order_id"], t["intent"],
                t["config_version"], t["duration_ms"], t["turns"], t["outcome"], t["summary"],
            )
            for t in traces
        ],
    )
    ev_rows = []
    for t in traces:
        tid = t["trace_id"]
        for e in events_by_trace[tid]:
            ev_rows.append(
                (
                    tid, e["seq"], e["type"], e["tool_name"], e["args_json"], e["result_json"],
                    e["latency_ms"], e["error"], e["content"],
                )
            )
    conn.executemany(
        "INSERT INTO events(trace_id, seq, type, tool_name, args_json, result_json, "
        "latency_ms, error, content) VALUES (?,?,?,?,?,?,?,?,?)",
        ev_rows,
    )
    conn.execute("COMMIT")
    conn.close()


def _write_world(path: Path, world: dict[str, Any]) -> None:
    conn = _open(path)
    conn.executescript(WORLD_SCHEMA)
    conn.execute("BEGIN")
    conn.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?,?)",
        [(o["order_id"], o["customer_id"], o["amount_cents"], o["currency"], o["placed_at"], o["status"]) for o in world["orders"]],
    )
    conn.executemany(
        "INSERT INTO refunds VALUES (?,?,?,?,?,?,?)",
        [
            (r["refund_id"], r["order_id"], r["amount_cents"], r["state"], r["requested_at"], r["completed_at"], r["processor_ref"])
            for r in world["refunds"]
        ],
    )
    conn.executemany(
        "INSERT INTO emails VALUES (?,?,?,?,?,?)",
        [(e["email_id"], e["order_id"], e["customer_id"], e["template"], e["sent_at"], e["idempotency_key"]) for e in world["emails"]],
    )
    conn.executemany(
        "INSERT INTO escalations VALUES (?,?,?,?,?,?)",
        [
            (x["escalation_id"], x["order_id"], x["customer_id"], x["reason"], x["created_at"], x["refund_state_at_escalation"])
            for x in world["escalations"]
        ],
    )
    conn.executemany("INSERT INTO world_meta VALUES (?,?)", sorted(world["meta"].items()))
    conn.execute("COMMIT")
    conn.close()


def write_worlds(worlds_by_trace: dict[str, dict[str, Any]]) -> None:
    paths.WORLDS_DIR.mkdir(parents=True, exist_ok=True)
    for trace_id in sorted(worlds_by_trace):
        _write_world(paths.world_path(trace_id), worlds_by_trace[trace_id])


def write_hidden_labels_db(path: Path, labels: dict[str, str]) -> None:
    conn = _open(path)
    conn.executescript(HIDDEN_LABELS_SCHEMA)
    conn.execute("BEGIN")
    conn.executemany("INSERT INTO hidden_labels VALUES (?,?)", sorted(labels.items()))
    conn.execute("COMMIT")
    conn.close()


def write_configs_db(path: Path, config: dict[str, Any]) -> None:
    conn = _open(path)
    conn.executescript(CONFIGS_SCHEMA)
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO agent_configs(version, created_at, model, system_prompt, tools_json, "
        "config_hash, status, parent_version, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            config["version"],
            config["created_at"],
            config["model"],
            config["system_prompt"],
            json.dumps(config["tools"], sort_keys=True, separators=(",", ":")),
            config["config_hash"],
            config["status"],
            config["parent_version"],
            config["notes"],
        ),
    )
    conn.execute("COMMIT")
    conn.close()
