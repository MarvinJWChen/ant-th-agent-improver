"""Generic trace featurisation.

Nothing in this module knows what a failure family is. It describes the shape of
a trace — how long, how many turns, which tools, repeated how often, with what
errors — and emits a token signature of the tool/result sequence. That
constraint is the point: a detector built on these features has to earn its
finds, and one seeded family is deliberately left with no rule of its own to see
whether it can.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from apps.api.contracts import TraceDetail
from apps.api.tool_registry import REGISTRY, effect_class

TOOLS = sorted(REGISTRY)

NUMERIC_FEATURES = [
    "n_events",
    "n_tool_calls",
    "n_distinct_tools",
    "turns",
    "log_duration",
    "max_repeat_tool",
    "max_repeat_identical_call",
    "n_timeouts",
    "n_errors",
    "has_escalation",
    "n_external_calls",
    "log_time_to_first_tool",
    "log_max_tool_latency",
    "mean_tool_latency",
    *[f"n_{t}" for t in TOOLS],
]


def _digest(args: dict | None) -> str:
    return hashlib.sha256(
        json.dumps(args or {}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:10]


@dataclass
class TraceFeatures:
    trace_id: str
    numeric: dict[str, float]
    signature: str
    tool_calls: list[tuple[str, dict]]

    def vector(self) -> list[float]:
        return [self.numeric.get(k, 0.0) for k in NUMERIC_FEATURES]


def _tok(s: str) -> str:
    return str(s).replace(" ", "_")[:32]


def extract(trace: TraceDetail) -> TraceFeatures:
    calls: list[tuple[str, dict]] = []
    tool_counts: dict[str, int] = {}
    identical: dict[tuple[str, str], int] = {}
    latencies: list[int] = []
    tokens: list[str] = [f"intent:{trace.intent}"]
    n_timeouts = n_errors = 0
    has_escalation = 0
    time_to_first_tool = 0
    elapsed = 0

    for ev in trace.events:
        if ev.type == "tool_call" and ev.tool_name:
            args = ev.args or {}
            calls.append((ev.tool_name, args))
            tool_counts[ev.tool_name] = tool_counts.get(ev.tool_name, 0) + 1
            k = (ev.tool_name, _digest(args))
            identical[k] = identical.get(k, 0) + 1
            tokens.append(f"call:{ev.tool_name}")
            if not time_to_first_tool:
                time_to_first_tool = max(elapsed, 1)
        elif ev.type == "tool_result" and ev.tool_name:
            latencies.append(ev.latency_ms)
            if ev.error:
                n_errors += 1
                tokens.append(f"err:{ev.tool_name}:{_tok(ev.error)}")
                if "timeout" in ev.error.lower():
                    n_timeouts += 1
            # Result payloads are featurised generically: any short scalar field
            # becomes a token. No field is special-cased.
            for kk, vv in (ev.result or {}).items():
                if isinstance(vv, str) and len(vv) <= 24:
                    tokens.append(f"res:{ev.tool_name}:{kk}={_tok(vv)}")
                elif isinstance(vv, bool):
                    tokens.append(f"res:{ev.tool_name}:{kk}={vv}")
        elif ev.type == "escalation":
            has_escalation = 1
            tokens.append("escalation")
        elapsed += ev.latency_ms

    if any(t == "escalate_to_human" for t, _ in calls):
        has_escalation = 1

    n_external = sum(1 for t, _ in calls if effect_class(t) == "external")
    numeric = {
        "n_events": float(len(trace.events)),
        "n_tool_calls": float(len(calls)),
        "n_distinct_tools": float(len(tool_counts)),
        "turns": float(trace.turns),
        "log_duration": math.log1p(trace.duration_ms),
        "max_repeat_tool": float(max(tool_counts.values(), default=0)),
        "max_repeat_identical_call": float(max(identical.values(), default=0)),
        "n_timeouts": float(n_timeouts),
        "n_errors": float(n_errors),
        "has_escalation": float(has_escalation),
        "n_external_calls": float(n_external),
        "log_time_to_first_tool": math.log1p(time_to_first_tool),
        "log_max_tool_latency": math.log1p(max(latencies, default=0)),
        "mean_tool_latency": float(sum(latencies) / len(latencies)) if latencies else 0.0,
    }
    for t in TOOLS:
        numeric[f"n_{t}"] = float(tool_counts.get(t, 0))

    return TraceFeatures(
        trace_id=trace.trace_id,
        numeric=numeric,
        signature=" ".join(tokens),
        tool_calls=calls,
    )
