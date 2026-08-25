"""Development fixtures behind the frozen API contract.

Everything here is a placeholder that exists so the browser journey is complete
from minute one. Each function is replaced by a real executable path as its
subsystem lands. /api/health reports which subsystems are real by inspecting the
actual state on disk, so the UI can label any remaining stub honestly.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

_RNG = random.Random(4242)
_PROMOTED: set[str] = set()

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def try_real_discovery(force: bool = False) -> dict[str, Any] | None:
    """Hook for the real detection pipeline; returns None until it lands."""
    try:
        from apps.api.detect import pipeline  # noqa: PLC0415
    except ImportError:
        return None
    from apps.api import store  # noqa: PLC0415

    if not store.corpus_available():
        return None
    return pipeline.discover(force=force).model_dump()


# ------------------------------------------------------------------ config stubs

_V1_PROMPT = (
    "You are a customer support agent for an online retailer. Your job is to "
    "resolve the customer's refund concern and make sure they receive their "
    "money. Look up the order, check on the refund, and take whatever action "
    "gets the customer paid. Keep the customer informed by email. If the "
    "customer seems unhappy or the situation is taking a long time, escalate to "
    "a human colleague. Be warm, brief, and decisive."
)

_V1_TOOLS = [
    {
        "name": "order_lookup",
        "description": "Look up an order by id.",
        "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
        "effect_class": "read",
    },
    {
        "name": "refund_status",
        "description": "Check and process the refund status for an order.",
        "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
        "effect_class": "read",
    },
    {
        "name": "refund_execute",
        "description": "Issue a refund for an order.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "amount_cents": {"type": "integer"}},
            "required": ["order_id", "amount_cents"],
        },
        "effect_class": "external",
    },
    {
        "name": "send_email",
        "description": "Send a templated email to the customer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "template": {"type": "string"},
                "order_id": {"type": "string"},
            },
            "required": ["customer_id", "template", "order_id"],
        },
        "effect_class": "external",
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate the conversation to a human support agent.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["order_id", "reason"],
        },
        "effect_class": "shadow_write",
    },
]


def _config(version: str = "v1", status: str = "active") -> dict[str, Any]:
    return {
        "version": version,
        "created_at": "2026-06-01T00:00:00Z",
        "model": "claude-opus-5",
        "system_prompt": _V1_PROMPT,
        "tools": _V1_TOOLS,
        "config_hash": _h(version, _V1_PROMPT),
        "status": status,
        "parent_version": None,
        "notes": "Seeded baseline configuration (fixture).",
    }


def configs() -> list[dict[str, Any]]:
    return [_config()]


def config(version: str) -> dict[str, Any]:
    return _config(version)


def agent_overview(live: bool) -> dict[str, Any]:
    return {
        "agent_name": "support-refund-agent",
        "active_config": _config(),
        "corpus": {
            "total_traces": 1000,
            "total_events": 11840,
            "window_start": "2026-06-01T00:11:00Z",
            "window_end": "2026-08-20T23:41:00Z",
            "outcome_counts": {"resolved": 862, "escalated": 118, "abandoned": 20},
            "intent_counts": {
                "refund_status_inquiry": 402,
                "refund_request": 361,
                "order_question": 158,
                "cancel_request": 79,
            },
            "p50_duration_ms": 24100,
            "p95_duration_ms": 96400,
            "escalation_rate": 0.118,
            "resolution_rate": 0.862,
        },
        "live_available": live,
    }


# ------------------------------------------------------------------ trace stubs

_INTENTS = ["refund_status_inquiry", "refund_request", "order_question", "cancel_request"]
_OUTCOMES = ["resolved", "resolved", "resolved", "escalated", "abandoned"]


def _trace_summary(i: int) -> dict[str, Any]:
    r = random.Random(i)
    ts = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(minutes=r.randint(0, 116000))
    return {
        "trace_id": f"tr_{i:06d}",
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "customer_id": f"cus_{r.randint(1, 900):04d}",
        "order_id": f"ord_{r.randint(10000, 19999)}",
        "intent": r.choice(_INTENTS),
        "duration_ms": r.randint(9000, 140000),
        "turns": r.randint(2, 9),
        "outcome": r.choice(_OUTCOMES),
        "summary": "Customer contacted support about an order.",
    }


def traces(limit: int) -> list[dict[str, Any]]:
    return [_trace_summary(i) for i in range(1, limit + 1)]


def trace(trace_id: str) -> dict[str, Any]:
    i = int(trace_id.split("_")[-1]) if trace_id.split("_")[-1].isdigit() else 1
    base = _trace_summary(i)
    oid = base["order_id"]
    events = [
        {"seq": 0, "type": "user_msg", "content": "Hi, where is my refund for order " + oid + "?", "latency_ms": 0},
        {"seq": 1, "type": "model_turn", "content": "Looking up the order.", "latency_ms": 1200},
        {"seq": 2, "type": "tool_call", "tool_name": "order_lookup", "args": {"order_id": oid}, "latency_ms": 0},
        {"seq": 3, "type": "tool_result", "tool_name": "order_lookup", "result": {"order_id": oid, "status": "delivered", "amount_cents": 4999}, "latency_ms": 120},
        {"seq": 4, "type": "tool_call", "tool_name": "refund_status", "args": {"order_id": oid}, "latency_ms": 0},
        {"seq": 5, "type": "tool_result", "tool_name": "refund_status", "result": {"state": "completed", "processor_ref": "pi_88c1"}, "latency_ms": 95},
        {"seq": 6, "type": "model_turn", "content": "Making sure the customer is refunded.", "latency_ms": 1400},
        {"seq": 7, "type": "tool_call", "tool_name": "refund_execute", "args": {"order_id": oid, "amount_cents": 4999}, "latency_ms": 0},
        {"seq": 8, "type": "tool_result", "tool_name": "refund_execute", "result": {"refund_id": "rf_2291", "state": "completed"}, "latency_ms": 890},
        {"seq": 9, "type": "agent_msg", "content": "Your refund has been issued.", "latency_ms": 700},
    ]
    return {**base, "config_version": "v1", "events": events}


# ------------------------------------------------------------------ discovery stub

_PATTERNS = [
    {
        "pattern_id": "P1",
        "cluster_id": 0,
        "title": "Refund-status inquiry escalates into a second refund",
        "signature": "refund_status → refund_execute on an order already refunded",
        "size": 78,
        "share_of_flagged": 0.35,
        "discovered_by": "evaluator+anomaly",
        "remediation_kind": "config",
        "top_features": ["repeat_refund_effects=2", "intent=refund_status_inquiry", "prior_refund_state=completed"],
        "exemplar_trace_ids": ["tr_000012", "tr_000047", "tr_000131"],
        "representative_evidence": [
            "refund_execute called on ord_10233 which already had a completed refund rf_1902",
            "refund_status returned state=completed immediately before the execute call",
        ],
        "impact": {"traces": 78, "est_double_refund_value_cents": 391_200, "share_of_corpus": 0.078},
    },
    {
        "pattern_id": "P2",
        "cluster_id": 1,
        "title": "Email timeout retry sends a second confirmation",
        "signature": "send_email(timeout) → send_email retry, no idempotency key",
        "size": 69,
        "share_of_flagged": 0.31,
        "discovered_by": "evaluator+anomaly",
        "remediation_kind": "code",
        "top_features": ["tool_timeouts=1", "repeat_send_email=2", "distinct_email_ids=2"],
        "exemplar_trace_ids": ["tr_000023", "tr_000088", "tr_000204"],
        "representative_evidence": [
            "send_email timed out after 11.4s, retried 2.1s later with a new message id",
            "two refund_confirmation emails exist for ord_11841",
        ],
        "impact": {"traces": 69, "duplicate_emails": 69, "share_of_corpus": 0.069},
    },
    {
        "pattern_id": "P3",
        "cluster_id": 2,
        "title": "Escalation raised while the refund is still inside SLA",
        "signature": "short trace → escalate_to_human with refund_state=processing, well inside SLA",
        "size": 71,
        "share_of_flagged": 0.32,
        "discovered_by": "anomaly-only",
        "remediation_kind": "process",
        "top_features": ["turns=3", "duration_ms<40000", "escalated=1", "hours_since_refund_request=26"],
        "exemplar_trace_ids": ["tr_000019", "tr_000105", "tr_000267"],
        "representative_evidence": [
            "escalated 26.4h after the refund request against a 48h SLA",
            "no refund_delay_notice email sent before escalating",
        ],
        "impact": {"traces": 71, "avoidable_escalations": 71, "share_of_corpus": 0.071},
    },
]


def discovery() -> dict[str, Any]:
    flagged = []
    for p in _PATTERNS:
        for j in range(min(p["size"], 24)):
            i = p["cluster_id"] * 1000 + j + 1
            t = _trace_summary(i)
            rule = p["discovered_by"] != "anomaly-only"
            hits = []
            if rule:
                hits.append(
                    {
                        "source": "evaluator",
                        "rule_id": "double_refund" if p["pattern_id"] == "P1" else "duplicate_confirmation",
                        "label": "Rule hit",
                        "detail": p["representative_evidence"][0],
                        "score": None,
                    }
                )
            hits.append(
                {
                    "source": "anomaly",
                    "rule_id": None,
                    "label": "Anomaly",
                    "detail": "Isolation score above threshold on generic trace features.",
                    "score": round(0.55 + _RNG.random() * 0.4, 3),
                }
            )
            flagged.append(
                {
                    "trace": t,
                    "hits": hits,
                    "anomaly_score": hits[-1]["score"],
                    "rule_flagged": rule,
                    "cluster_id": p["cluster_id"],
                }
            )
    return {
        "computed_at": _now(),
        "corpus_hash": _h("fixture-corpus"),
        "n_traces_scanned": 1000,
        "n_flagged": 218,
        "n_rule_flagged": 147,
        "n_anomaly_only": 71,
        "anomaly_threshold": 0.62,
        "cluster_k": 3,
        "silhouette": 0.41,
        "patterns": _PATTERNS,
        "flagged": flagged,
    }


# ------------------------------------------------------------------ LLM stubs


def _prov(task: str, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "task": task,
        "task_version": "fixture.0",
        "model": "claude-opus-5",
        "created_at": _now(),
        "verified": False,
        "stale_reason": "Development fixture — not produced by a real model run.",
        "hashes": {"inputs_hash": _h(task, mode)[:16], "agent_config_hash": _h("v1")[:16]},
        "expected_hashes": None,
        "latency_ms": 900 if mode == "live" else None,
    }


_DIAGNOSES = {
    "P1": {
        "root_cause": "The `refund_status` tool description says it will 'check and process' the refund status, and the system prompt tells the agent to 'take whatever action gets the customer paid'. Together these read as permission to issue a refund during a status inquiry.",
        "mechanism": "Customer asks where their refund is → agent calls refund_status → sees state=completed but interprets its own role as ensuring payment → calls refund_execute on the same order → a second refund is issued against an order that was already refunded.",
        "why_it_recurs": "Nothing in the configuration distinguishes a read from a write, and no precondition requires checking for an existing refund before issuing one. The failure is deterministic given a status inquiry on an already-refunded order.",
        "confidence": "high",
        "remediation_kind": "config",
        "remediation_summary": "Disambiguate refund_status as read-only and add an explicit no-prior-refund precondition to refund_execute.",
    },
    "P2": {
        "root_cause": "`send_email` has no idempotency parameter, so an ambiguous timeout is indistinguishable from a genuine failure and the retry produces a second delivery.",
        "mechanism": "send_email times out after ~11s with no acknowledgement → the agent cannot tell whether the mail was sent → it retries → the email service accepts the second request as a new message → the customer receives two refund confirmations.",
        "why_it_recurs": "The ambiguity is in the tool's contract, not the agent's reasoning. No prompt wording can make a non-idempotent call safe to retry.",
        "confidence": "high",
        "remediation_kind": "code",
        "remediation_summary": "Add a caller-supplied idempotency key to the email tool and deduplicate on it.",
    },
    "P3": {
        "root_cause": "The agent has no notion of the refund SLA, so 'taking a long time' is judged against customer sentiment rather than against the 48-hour commitment.",
        "mechanism": "Refund sits in processing → customer expresses frustration ~26h in → the prompt instructs escalation when the customer seems unhappy → the agent escalates while the refund is still well inside SLA, with no delay notice sent.",
        "why_it_recurs": "The escalation trigger is subjective and the agent is never given the SLA or the option to set expectations instead.",
        "confidence": "medium",
        "remediation_kind": "process",
        "remediation_summary": "Give the agent the SLA clock, require a delay notice first, and only escalate on genuine breach.",
    },
}


def diagnose(pattern_id: str, mode: str) -> dict[str, Any]:
    d = _DIAGNOSES.get(pattern_id, _DIAGNOSES["P1"])
    pat = next((p for p in _PATTERNS if p["pattern_id"] == pattern_id), _PATTERNS[0])
    return {
        "diagnosis": {"pattern_id": pattern_id, "cited_trace_ids": pat["exemplar_trace_ids"], **d},
        "provenance": _prov("diagnose_pattern", mode),
    }


_PROMPT_V2 = (
    "You are a customer support agent for an online retailer.\n\n"
    "Tool semantics are strict: `refund_status` is READ-ONLY and never moves "
    "money. `refund_execute` is the only tool that issues a refund, and issuing "
    "a refund is irreversible.\n\n"
    "Before calling `refund_execute` you MUST call `refund_status` and confirm "
    "the state is not `completed` or `processing`. If a refund already exists, "
    "report its status to the customer and stop.\n\n"
    "The refund SLA is 48 hours from the request. If a refund is still "
    "processing inside the SLA, tell the customer when to expect it. Escalate to "
    "a human only when the SLA has been breached, the refund has failed, or the "
    "customer explicitly asks for a person.\n\n"
    "Be warm, brief, and precise."
)

_CODE_DIFF = """--- a/tools/email_tool.py
+++ b/tools/email_tool.py
@@ -1,20 +1,38 @@
 import uuid
+import hashlib
 from typing import Any
 
 from services.mailer import Mailer
+from services.store import kv
 
 mailer = Mailer()
 
 
-def send_email(customer_id: str, template: str, order_id: str) -> dict[str, Any]:
-    \"\"\"Send a templated email to the customer.\"\"\"
-    message_id = str(uuid.uuid4())
-    mailer.deliver(
-        message_id=message_id,
-        customer_id=customer_id,
-        template=template,
-        context={"order_id": order_id},
-    )
-    return {"message_id": message_id, "delivered": True}
+def _derive_key(customer_id: str, template: str, order_id: str) -> str:
+    raw = f"{customer_id}:{template}:{order_id}"
+    return hashlib.sha256(raw.encode()).hexdigest()[:32]
+
+
+def send_email(
+    customer_id: str,
+    template: str,
+    order_id: str,
+    idempotency_key: str | None = None,
+) -> dict[str, Any]:
+    \"\"\"Send a templated email exactly once per (customer, template, order).
+
+    A timeout is ambiguous: the mail may or may not have gone out. Retrying with
+    the same idempotency key is therefore safe, because the second call returns
+    the first call's result instead of delivering again.
+    \"\"\"
+    key = idempotency_key or _derive_key(customer_id, template, order_id)
+
+    existing = kv.get(f"email:{key}")
+    if existing is not None:
+        return {**existing, "deduplicated": True}
+
+    message_id = str(uuid.uuid4())
+    kv.put(f"email:{key}", {"message_id": message_id, "delivered": True}, ttl=86_400)
+    mailer.deliver(
+        message_id=message_id,
+        customer_id=customer_id,
+        template=template,
+        context={"order_id": order_id},
+        idempotency_key=key,
+    )
+    return {"message_id": message_id, "delivered": True, "deduplicated": False}
"""


def _config_patch(candidate: str) -> dict[str, Any]:
    if candidate == "a":
        after = (
            _V1_PROMPT
            + "\n\nNever issue a refund without explicit confirmation from the customer "
            "in this conversation. If you are unsure about anything, escalate to a human."
        )
        return {
            "system_prompt_before": _V1_PROMPT,
            "system_prompt_after": after,
            "tool_description_edits": [
                {
                    "tool_name": "refund_status",
                    "before": "Check and process the refund status for an order.",
                    "after": "Check the refund status for an order.",
                }
            ],
            "rationale": "Require explicit confirmation before any refund, and soften the status tool's wording.",
            "expected_effect": "Eliminates unrequested second refunds.",
            "risks": ["Blanket confirmation requirement may block legitimate refunds and push them to humans."],
        }
    return {
        "system_prompt_before": _V1_PROMPT,
        "system_prompt_after": _PROMPT_V2,
        "tool_description_edits": [
            {
                "tool_name": "refund_status",
                "before": "Check and process the refund status for an order.",
                "after": "READ-ONLY. Return the current refund state for an order. This tool never moves money and never issues a refund.",
            },
            {
                "tool_name": "refund_execute",
                "before": "Issue a refund for an order.",
                "after": "Issue a refund for an order. Irreversible. Only call this after refund_status confirms no refund exists in state completed or processing.",
            },
        ],
        "rationale": "Separate reading a refund from issuing one, and make the no-prior-refund precondition explicit.",
        "expected_effect": "Removes the second-refund path without changing behaviour on genuine refund requests.",
        "risks": ["Adds a mandatory status check before every refund, costing one extra tool call."],
    }


def patch(pattern_id: str, mode: str) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "candidate_version": "v2-candidate-a",
                "parent_version": "v1",
                "config_hash": _h("cand-a"),
                "patch": _config_patch("a"),
                "within_edit_boundary": True,
                "boundary_report": ["system_prompt: changed", "tools[refund_status].description: changed"],
                "label": "Confirmation-first (broad)",
            },
            {
                "candidate_version": "v2-candidate-b",
                "parent_version": "v1",
                "config_hash": _h("cand-b"),
                "patch": _config_patch("b"),
                "within_edit_boundary": True,
                "boundary_report": [
                    "system_prompt: changed",
                    "tools[refund_status].description: changed",
                    "tools[refund_execute].description: changed",
                ],
                "label": "Read/write separation (surgical)",
            },
        ],
        "provenance": _prov("propose_config_patch", mode),
    }


def propose(pattern_id: str, mode: str) -> dict[str, Any]:
    if pattern_id == "P2":
        return {
            "kind": "code",
            "code": {
                "file_path": "tools/email_tool.py",
                "unified_diff": _CODE_DIFF,
                "rationale": "A timeout leaves delivery ambiguous. Making the call idempotent on a derived key makes the retry safe by construction, rather than asking the agent to guess.",
                "test_note": "Add a test that calls send_email twice with the same arguments and asserts Mailer.deliver is invoked once.",
            },
            "process": None,
            "config": None,
            "provenance": _prov("propose_code_change", mode),
        }
    if pattern_id == "P3":
        return {
            "kind": "process",
            "code": None,
            "process": {
                "problem_statement": "71 escalations were raised while the refund was still inside the 48-hour SLA, consuming human support capacity without changing the outcome for the customer.",
                "steps": [
                    {"title": "Expose the SLA clock to the agent", "detail": "Return hours_elapsed and sla_hours from refund_status so the agent can reason about lateness instead of sentiment."},
                    {"title": "Require a delay notice before escalating", "detail": "Send refund_delay_notice with a concrete expected date; only escalate if the customer replies again after that."},
                    {"title": "Gate escalation on SLA breach", "detail": "Escalate on breach, failed refund, or explicit customer request — not on frustration alone."},
                    {"title": "Investigate processor latency", "detail": "p95 refund completion is the upstream driver; track it as a reliability metric with the payments team."},
                ],
                "owners": ["Support Platform", "Payments Reliability"],
                "metrics": ["in-SLA escalation rate", "p95 refund completion time", "repeat-contact rate after a delay notice"],
                "rationale": "The agent is behaving reasonably given what it knows. The fix is to give it the SLA and a cheaper intermediate action, plus to attack the latency that creates the anxiety.",
            },
            "config": None,
            "provenance": _prov("propose_process_change", mode),
        }
    return {
        "kind": "config",
        "code": None,
        "process": None,
        "config": _config_patch("b"),
        "provenance": _prov("propose_config_patch", mode),
    }


# ------------------------------------------------------------------ replay stub

_RUNS: dict[str, dict[str, Any]] = {}


def _ledger(tools: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    out = []
    for i, (tool, eff, disp) in enumerate(tools):
        out.append(
            {
                "seq": i,
                "tool": tool,
                "effect_class": eff,
                "target": "ord_10233",
                "args_digest": _h(tool, str(i))[:12],
                "disposition": disp,
                "external": eff == "external",
                "note": None,
            }
        )
    return out


def _arm(arm: str, trace_id: str, double: bool) -> dict[str, Any]:
    tools = [("order_lookup", "read", "APPLIED_TO_CLONE"), ("refund_status", "read", "APPLIED_TO_CLONE")]
    steps = [
        {"seq": 0, "kind": "model_turn", "text": "Checking the order and its refund.", "diverged": False},
        {"seq": 1, "kind": "tool_call", "tool_name": "order_lookup", "args": {"order_id": "ord_10233"}, "diverged": False},
        {"seq": 2, "kind": "tool_call", "tool_name": "refund_status", "args": {"order_id": "ord_10233"}, "diverged": False},
    ]
    if double:
        tools += [("refund_execute", "external", "SHADOWED"), ("send_email", "external", "SHADOWED")]
        steps += [
            {"seq": 3, "kind": "model_turn", "text": "Making sure the customer is refunded.", "diverged": True},
            {"seq": 4, "kind": "tool_call", "tool_name": "refund_execute", "args": {"order_id": "ord_10233", "amount_cents": 4999}, "diverged": True},
            {"seq": 5, "kind": "agent_msg", "text": "Your refund has been issued.", "diverged": True},
        ]
    else:
        steps += [
            {"seq": 3, "kind": "model_turn", "text": "A refund already exists in state completed; reporting it.", "diverged": True},
            {"seq": 4, "kind": "agent_msg", "text": "Your refund of $49.99 completed on 12 July; it should appear within two business days.", "diverged": True},
        ]
    return {
        "arm": arm,
        "trace_id": trace_id,
        "clone_path": f"/tmp/replay/{arm}/{trace_id}.sqlite",
        "clone_sha256": _h(arm, trace_id),
        "source_world_sha256": _h("world", trace_id),
        "execution": "replayed" if arm == "baseline" else "re-executed",
        "steps": steps,
        "ledger": _ledger(tools),
        "unsafe_effects": 0,
        "external_calls_executed": 0,
        "outcome": "resolved",
        "turns": len([s for s in steps if s["kind"] == "model_turn"]),
    }


def replay_run(pattern_id: str, candidate_version: str, mode: str) -> dict[str, Any]:
    fails = candidate_version.endswith("candidate-a")
    run_id = f"run_{candidate_version}"
    target = [f"tr_{i:06d}" for i in range(1, 13)]
    control = [f"tr_{i:06d}" for i in range(500, 512)]
    pairs = []
    for i, tid in enumerate(target):
        pairs.append(
            {
                "trace_id": tid,
                "cohort": "target",
                "baseline": _arm("baseline", tid, True),
                "candidate": _arm("candidate", tid, False),
                "trajectory_diverged": True,
                "baseline_pass": False,
                "candidate_pass": True,
                "regression": False,
            }
        )
    for i, tid in enumerate(control):
        broke = fails and i < 3
        pairs.append(
            {
                "trace_id": tid,
                "cohort": "control",
                "baseline": _arm("baseline", tid, False),
                "candidate": _arm("candidate", tid, False),
                "trajectory_diverged": broke,
                "baseline_pass": True,
                "candidate_pass": not broke,
                "regression": broke,
            }
        )
    n_reg = sum(1 for p in pairs if p["regression"])
    checks = [
        {
            "id": "target_improvement",
            "label": "Target failure rate improved",
            "status": "pass",
            "detail": "double_refund_rate on the target cohort: 1.000 → 0.000 (−100%).",
            "evidence": target[:3],
        },
        {
            "id": "control_preservation",
            "label": "No regression on passing controls",
            "status": "fail" if n_reg else "pass",
            "detail": (
                f"{n_reg} control trace(s) passed at baseline and fail under the candidate."
                if n_reg
                else "All 12 control traces that passed at baseline still pass."
            ),
            "evidence": [p["trace_id"] for p in pairs if p["regression"]],
        },
        {
            "id": "effect_safety",
            "label": "Zero unsafe external effects",
            "status": "pass",
            "detail": "0 unknown-effect blocks, 0 external calls executed; 48 external effects shadowed.",
            "evidence": [],
        },
        {
            "id": "provenance",
            "label": "Capture provenance valid",
            "status": "pending",
            "detail": "Provenance validation lands with the real capture pipeline.",
            "evidence": [],
        },
    ]
    verdict = "fail" if any(c["status"] == "fail" for c in checks) else "pending"
    run = {
        "run_id": run_id,
        "pattern_id": pattern_id,
        "candidate_version": candidate_version,
        "baseline_version": "v1",
        "mode": mode,
        "started_at": _now(),
        "finished_at": _now(),
        "cohort_target": target,
        "cohort_control": control,
        "world_isolation": {
            "worlds_frozen": 24,
            "clones_created": 48,
            "source_worlds_mutated": 0,
            "note": "Each arm runs against its own file-level copy of the frozen world.",
        },
        "baseline_metrics": {
            "double_refund_rate": 1.0,
            "duplicate_confirmation_rate": 0.0,
            "premature_escalation_rate": 0.0,
            "resolution_rate": 1.0,
            "avg_turns": 3.0,
            "unsafe_effects": 0,
            "external_calls_executed": 0,
        },
        "candidate_metrics": {
            "double_refund_rate": 0.0,
            "duplicate_confirmation_rate": 0.0,
            "premature_escalation_rate": 0.25 if fails else 0.0,
            "resolution_rate": 0.75 if fails else 1.0,
            "avg_turns": 2.0,
            "unsafe_effects": 0,
            "external_calls_executed": 0,
        },
        "pairs": pairs,
        "gate": {"verdict": verdict, "checks": checks, "promotable": False},
        "provenance": _prov("counterfactual_run", mode),
        "promoted": run_id in _PROMOTED,
    }
    _RUNS[run_id] = run
    return run


def replay_get(run_id: str) -> dict[str, Any] | None:
    run = _RUNS.get(run_id)
    if run:
        run["promoted"] = run_id in _PROMOTED
    return run


def promote(run_id: str) -> dict[str, Any] | None:
    run = _RUNS.get(run_id)
    if run is None:
        return None
    gate = run["gate"]
    if not gate["promotable"]:
        return {
            "promoted": False,
            "active_version": "v1",
            "message": "Promotion blocked: the gate has not passed.",
            "gate": gate,
        }
    _PROMOTED.add(run_id)
    return {
        "promoted": True,
        "active_version": run["candidate_version"],
        "message": "Candidate promoted to active.",
        "gate": gate,
    }
