"""Observable failure signals.

Every signal here is stated in terms that apply to any tool-using agent, not to
this one: the agent failed to finish, a tool timed out and was retried, the same
effect-producing call was issued twice against the same target. None of them
name a refund, an email, or an SLA.

That constraint is deliberate and load-bearing. If a signal encoded "two refunds
on one order", then finding the double-refund family would prove nothing — we
would have told the system what to look for. Because these are generic, the
seeded families have to be recovered from behaviour alone, and how well that
works is measured offline in scripts/validate_detection.py against labels this
package cannot reach.
"""
from __future__ import annotations

from collections import defaultdict

from apps.api.contracts import EvidenceHit, TraceDetail
from apps.api.detect.features import TraceFeatures
from apps.api.tool_registry import effect_class

# A trace this far above its peers on turns or duration is worth a look even if
# it eventually succeeded.
SLOW_PEER_MULTIPLE = 2.5


def incomplete_handling(trace: TraceDetail, f: TraceFeatures) -> EvidenceHit | None:
    """The agent did not finish the job itself."""
    if trace.outcome == "resolved":
        return None
    return EvidenceHit(
        source="evaluator",
        rule_id="incomplete_handling",
        label="Agent did not resolve the request",
        detail=(
            f"Trace ended as {trace.outcome} after {trace.turns} turns and "
            f"{trace.duration_ms / 1000:.1f}s."
        ),
    )


def repeated_effect(trace: TraceDetail, f: TraceFeatures) -> EvidenceHit | None:
    """The same effect-producing call was issued more than once at the same target.

    Reads are free to repeat. A call that changes state or leaves our boundary is
    not, because the second one lands a second time.
    """
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for ev in trace.events:
        if ev.type != "tool_call" or not ev.tool_name:
            continue
        if effect_class(ev.tool_name) == "read":
            continue
        args = ev.args or {}
        target = str(args.get("order_id") or args.get("customer_id") or "")
        seen[(ev.tool_name, target)] += 1

    for (tool, target), n in seen.items():
        if n > 1:
            return EvidenceHit(
                source="evaluator",
                rule_id="repeated_effect",
                label="Effect repeated at the same target",
                detail=(
                    f"`{tool}` ({effect_class(tool)}) was called {n}× against {target or 'the same target'} "
                    "within one trace."
                ),
            )
    return None


# Generic status vocabulary. Any tool that reports work as finished tends to use
# one of these words; none of them is specific to this agent's domain.
TERMINAL_STATES = {"completed", "succeeded", "success", "done", "fulfilled", "closed", "settled"}


def redundant_effect(trace: TraceDetail, f: TraceFeatures) -> EvidenceHit | None:
    """An effect issued at a target the trace had already read as finished.

    This is the same "repeated effect" idea as above, except the first occurrence
    is visible in a read rather than in an earlier call: the agent looked, was
    told the work was already done, and did it anyway. Stated in terms of effect
    classes and generic status vocabulary, so it carries no domain knowledge.
    """
    finished: dict[str, tuple[str, str]] = {}
    for ev in trace.events:
        # Only a *read* establishes prior state. An effect's own success result
        # must not make later effects look redundant.
        if (
            ev.type == "tool_result"
            and ev.tool_name
            and ev.result
            and effect_class(ev.tool_name) == "read"
        ):
            target = str(ev.result.get("order_id") or ev.result.get("customer_id") or trace.order_id)
            for key, val in ev.result.items():
                if isinstance(val, str) and val.lower() in TERMINAL_STATES:
                    finished[target] = (ev.tool_name, f"{key}={val}")
        elif ev.type == "tool_call" and ev.tool_name and effect_class(ev.tool_name) != "read":
            args = ev.args or {}
            target = str(args.get("order_id") or args.get("customer_id") or "")
            if target in finished:
                src, state = finished[target]
                return EvidenceHit(
                    source="evaluator",
                    rule_id="redundant_effect",
                    label="Effect issued at an already-finished target",
                    detail=(
                        f"`{ev.tool_name}` ({effect_class(ev.tool_name)}) was called on {target} at "
                        f"event {ev.seq}, after `{src}` had already reported {state}."
                    ),
                )
    return None


def ambiguous_retry(trace: TraceDetail, f: TraceFeatures) -> EvidenceHit | None:
    """A tool timed out — outcome unknown — and was called again anyway."""
    timed_out: set[str] = set()
    for ev in trace.events:
        if ev.type == "tool_result" and ev.error and "timeout" in ev.error.lower() and ev.tool_name:
            timed_out.add(ev.tool_name)
        elif ev.type == "tool_call" and ev.tool_name in timed_out:
            if effect_class(ev.tool_name) == "read":
                continue
            return EvidenceHit(
                source="evaluator",
                rule_id="ambiguous_retry",
                label="Retry after an ambiguous timeout",
                detail=(
                    f"`{ev.tool_name}` timed out with no acknowledgement and was called again at "
                    f"event {ev.seq}. A timeout does not mean the effect did not land."
                ),
            )
    return None


def peer_relative_cost(trace: TraceDetail, f: TraceFeatures, peers: dict[str, float]) -> EvidenceHit | None:
    """Far more expensive than other traces handling the same kind of request."""
    base = peers.get(trace.intent, 0.0)
    if base <= 0:
        return None
    ratio = trace.duration_ms / base
    if ratio < SLOW_PEER_MULTIPLE:
        return None
    return EvidenceHit(
        source="evaluator",
        rule_id="peer_relative_cost",
        label="Far slower than same-intent peers",
        detail=(
            f"{trace.duration_ms / 1000:.1f}s against a median of {base / 1000:.1f}s for "
            f"{trace.intent} ({ratio:.1f}× peers)."
        ),
    )


def evaluate(
    trace: TraceDetail, f: TraceFeatures, peer_medians: dict[str, float] | None = None
) -> list[EvidenceHit]:
    hits = [
        hit
        for rule in (incomplete_handling, repeated_effect, redundant_effect, ambiguous_retry)
        if (hit := rule(trace, f)) is not None
    ]
    if peer_medians:
        cost = peer_relative_cost(trace, f, peer_medians)
        if cost:
            hits.append(cost)
    return hits


def peer_medians(traces: list[TraceDetail]) -> dict[str, float]:
    by_intent: dict[str, list[int]] = defaultdict(list)
    for t in traces:
        by_intent[t.intent].append(t.duration_ms)
    return {k: sorted(v)[len(v) // 2] for k, v in by_intent.items() if v}
