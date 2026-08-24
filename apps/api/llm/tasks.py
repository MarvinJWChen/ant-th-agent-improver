"""Versioned LLM tasks.

Each task owns its prompt, its output schema, and a version string. Live mode
and cached mode both go through these definitions — cached mode short-circuits
at the transport call, not before it — which is what lets a capture claim to be
the output of *this* code path rather than a hand-written fixture.

Bump a task's version whenever its prompt or schema changes. Existing captures
then stop validating, which is the intended behaviour: they were produced by a
different program.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

_S = {"type": "string"}
_SL = {"type": "array", "items": {"type": "string"}}


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


DIAGNOSE_SCHEMA = _obj(
    {
        "verdict": {"type": "string", "enum": ["failure", "expected_behaviour"]},
        "root_cause": _S,
        "mechanism": _S,
        "why_it_recurs": _S,
        "cited_trace_ids": _SL,
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "remediation_kind": {"type": "string", "enum": ["code", "process", "config", "none"]},
        "remediation_summary": _S,
    },
    ["verdict", "root_cause", "mechanism", "why_it_recurs", "cited_trace_ids", "confidence",
     "remediation_kind", "remediation_summary"],
)

PATCH_SCHEMA = _obj(
    {
        "candidates": {
            "type": "array",
            "items": _obj(
                {
                    "label": _S,
                    "system_prompt_after": _S,
                    "tool_description_edits": {
                        "type": "array",
                        "items": _obj(
                            {"tool_name": _S, "after": _S},
                            ["tool_name", "after"],
                        ),
                    },
                    "rationale": _S,
                    "expected_effect": _S,
                    "risks": _SL,
                },
                ["label", "system_prompt_after", "tool_description_edits", "rationale",
                 "expected_effect", "risks"],
            ),
        }
    },
    ["candidates"],
)

CODE_SCHEMA = _obj(
    {"file_path": _S, "unified_diff": _S, "rationale": _S, "test_note": _S},
    ["file_path", "unified_diff", "rationale", "test_note"],
)

PROCESS_SCHEMA = _obj(
    {
        "problem_statement": _S,
        "steps": {
            "type": "array",
            "items": _obj({"title": _S, "detail": _S}, ["title", "detail"]),
        },
        "owners": _SL,
        "metrics": _SL,
        "rationale": _S,
    },
    ["problem_statement", "steps", "owners", "metrics", "rationale"],
)


@dataclass(frozen=True)
class Task:
    name: str
    version: str
    schema: dict[str, Any]
    build: Callable[[dict[str, Any]], tuple[str, str]]


# ---------------------------------------------------------------- prompt bodies

_ANALYST_SYSTEM = (
    "You are a staff engineer doing incident analysis on a production LLM agent. "
    "You are given a cluster of real traces that a detection pipeline flagged as "
    "worth investigating, plus the agent's current configuration.\n\n"
    "Work only from the evidence supplied. Cite specific trace ids. Do not invent "
    "traces, tools, metrics, or code you were not shown. If the evidence is thin, "
    "say so through the confidence field rather than padding the analysis.\n\n"
    "Be concrete and mechanical: name the exact configuration wording or tool "
    "contract that produces the behaviour."
)


def _render_config(cfg: dict[str, Any]) -> str:
    lines = [f"model: {cfg['model']}", "", "system_prompt:", cfg["system_prompt"], "", "tools:"]
    for t in cfg["tools"]:
        lines.append(f"  - name: {t['name']}")
        lines.append(f"    description: {t['description']}")
        lines.append(f"    effect_class: {t.get('effect_class', 'unknown')}")
        lines.append(f"    input_schema: {json.dumps(t['input_schema'])}")
    return "\n".join(lines)


def _render_traces(traces: list[dict[str, Any]]) -> str:
    out = []
    for t in traces:
        out.append(f"--- trace {t['trace_id']} | intent={t['intent']} | outcome={t['outcome']} "
                   f"| turns={t['turns']} | duration_ms={t['duration_ms']}")
        for e in t["events"]:
            if e["type"] == "tool_call":
                out.append(f"  [{e['seq']}] CALL {e['tool_name']} {json.dumps(e.get('args') or {})}")
            elif e["type"] == "tool_result":
                err = f" ERROR={e['error']}" if e.get("error") else ""
                out.append(
                    f"  [{e['seq']}] RESULT {e['tool_name']} {json.dumps(e.get('result') or {})}"
                    f" ({e.get('latency_ms', 0)}ms){err}"
                )
            elif e["type"] in ("user_msg", "agent_msg", "escalation"):
                out.append(f"  [{e['seq']}] {e['type'].upper()}: {(e.get('content') or '')[:220]}")
    return "\n".join(out)


def _render_pattern(p: dict[str, Any]) -> str:
    return (
        f"pattern_id: {p['pattern_id']}\n"
        f"size: {p['size']} traces ({p['share_of_flagged']:.0%} of all flagged)\n"
        f"discovered_by: {p['discovered_by']}\n"
        f"cluster signature (from generic trace features): {p['signature']}\n"
        f"top distinguishing features: {', '.join(p['top_features'])}\n"
        f"evidence samples:\n  - " + "\n  - ".join(p["representative_evidence"])
    )


def _diagnose_build(inp: dict[str, Any]) -> tuple[str, str]:
    user = (
        "## Discovered behaviour cluster\n\n"
        + _render_pattern(inp["pattern"])
        + "\n\n## Agent configuration currently in production\n\n"
        + _render_config(inp["config"])
        + "\n\n## Example traces from this cluster\n\n"
        + _render_traces(inp["traces"])
        + "\n\n## Task\n\n"
        "The clustering step groups traces by behaviour. It has no idea whether a "
        "cluster is a problem — that judgement is yours.\n\n"
        "**First decide `verdict`.** Some clusters are simply uncommon but correct: "
        "the agent did the right thing and the behaviour merely looks unusual next to "
        "the bulk of traffic. If that is what you are looking at, answer "
        "`expected_behaviour`, set `remediation_kind` to `none`, and use the other "
        "fields to explain why the behaviour is correct. Do not invent a defect to "
        "have something to report.\n\n"
        "If it is a genuine `failure`, describe the mechanism step by step, explain "
        "why it recurs rather than being a one-off, and choose the remediation that "
        "would actually remove it:\n\n"
        "- `code` — a tool's implementation or contract is itself unsafe, so no "
        "instruction to the agent can make it correct. The clearest case is an "
        "operation that cannot be retried safely.\n"
        "- `process` — the agent behaved reasonably given what it was told, and the "
        "fix is operational: information it was never given, an upstream reliability "
        "problem, or a policy that does not exist yet.\n"
        "- `config` — the agent had everything it needed, and the failure comes from "
        "ambiguous or missing wording in the system prompt or a tool description. "
        "Choose this only when rewording genuinely removes the failure.\n\n"
        "Judge each of these on its merits. Do not assume the answer is `config` "
        "because that is the easiest thing to change."
    )
    return _ANALYST_SYSTEM, user


def _patch_build(inp: dict[str, Any]) -> tuple[str, str]:
    system = (
        _ANALYST_SYSTEM
        + "\n\nYou are now writing configuration patches. Hard boundary: you may only "
        "rewrite the system prompt and the `description` field of existing tools. You "
        "may not add, remove, or rename tools, and you may not change any input schema. "
        "A patch that violates this is rejected automatically."
    )
    user = (
        "## Diagnosis\n\n"
        + json.dumps(inp["diagnosis"], indent=2)
        + "\n\n## Current configuration\n\n"
        + _render_config(inp["config"])
        + "\n\n## Task\n\n"
        "Produce exactly two candidate patches:\n\n"
        "1. A **broad** candidate that a hurried engineer would plausibly write: it "
        "addresses the target failure by adding a blanket safety requirement, and it "
        "is genuinely likely to cause collateral damage on unrelated healthy traffic "
        "(for example by escalating to a human whenever anything is uncertain). Be "
        "honest about that in its risks.\n\n"
        "2. A **surgical** candidate that fixes the specific mechanism identified in "
        "the diagnosis and changes nothing else.\n\n"
        "For each, give the complete replacement system prompt (not a diff) and the "
        "complete replacement text for each tool description you change."
    )
    return system, user


def _code_build(inp: dict[str, Any]) -> tuple[str, str]:
    system = (
        _ANALYST_SYSTEM
        + "\n\nYou are now proposing a code change. Output a valid unified diff with "
        "correct `---`/`+++`/`@@` headers. The change must be small, reviewable, and "
        "self-evidently correct."
    )
    user = (
        "## Diagnosis\n\n"
        + json.dumps(inp["diagnosis"], indent=2)
        + "\n\n## Current implementation of the tool at fault\n\n"
        "```python\n" + inp["source"] + "```\n\n"
        "## Task\n\n"
        "Propose the code change that removes this failure mode at the source, as a "
        "unified diff against the file shown. Explain why the fix belongs in code "
        "rather than in the agent's prompt, and state the one test that would prove it."
    )
    return system, user


def _process_build(inp: dict[str, Any]) -> tuple[str, str]:
    system = (
        _ANALYST_SYSTEM
        + "\n\nYou are now proposing an operational remediation. This pattern is not "
        "fixable by prompt or code alone. Recommend concrete, assignable steps."
    )
    user = (
        "## Diagnosis\n\n"
        + json.dumps(inp["diagnosis"], indent=2)
        + "\n\n## Pattern\n\n"
        + _render_pattern(inp["pattern"])
        + "\n\n## Example traces\n\n"
        + _render_traces(inp["traces"])
        + "\n\n## Task\n\n"
        "Propose a remediation combining process, tool reliability, and customer "
        "communication. State the problem in terms of cost to the support "
        "organisation, give ordered steps with owners, and name the metrics that would "
        "show the change worked."
    )
    return system, user


TASKS: dict[str, Task] = {
    "diagnose_pattern": Task("diagnose_pattern", "2026-08-24.2", DIAGNOSE_SCHEMA, _diagnose_build),
    "propose_config_patch": Task("propose_config_patch", "2026-08-24.1", PATCH_SCHEMA, _patch_build),
    "propose_code_change": Task("propose_code_change", "2026-08-24.1", CODE_SCHEMA, _code_build),
    "propose_process_change": Task("propose_process_change", "2026-08-24.1", PROCESS_SCHEMA, _process_build),
}
