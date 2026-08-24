"""The refund agent itself: a Claude tool-use loop we own end to end.

Owning the loop is what makes the whole replay claim possible. Every tool call
the model makes is dispatched through a ToolHost bound to one cloned world, so
the agent is free to take whatever trajectory it likes while remaining unable to
reach anything real.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from apps.api.contracts import ArmTrajectoryStep
from apps.api.replay.ledger import UnknownEffectError
from apps.api.replay.tools import ToolHost

MODEL = "claude-opus-5"
MAX_TOKENS = 8192
EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Bumped whenever the loop's request shape changes in a way that could alter a
# trajectory. Captured runs record it, and a capture from a different loop
# version is rejected as incompatible.
AGENT_LOOP_VERSION = "2026-08-24.1"


class LiveInferenceUnavailable(RuntimeError):
    pass


@dataclass
class AgentRunResult:
    steps: list[ArmTrajectoryStep] = field(default_factory=list)
    turns: int = 0
    stopped_because: str = "end_turn"
    aborted_by_unknown_effect: bool = False


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LiveInferenceUnavailable("ANTHROPIC_API_KEY is not set")
    import anthropic  # imported lazily so cached mode needs no SDK credentials

    return anthropic.Anthropic()


def _create(client, **kw):
    """Prefer the server-side refusal fallback; degrade cleanly if unavailable."""
    try:
        return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kw)
    except Exception as e:  # noqa: BLE001 - beta may not be enabled on this org
        msg = str(e).lower()
        if "beta" not in msg and "fallback" not in msg and "unexpected" not in msg:
            raise
        return client.messages.create(**kw)


def run_agent(
    *,
    system_prompt: str,
    tools: list[dict[str, Any]],
    user_message: str,
    host: ToolHost,
    max_turns: int = 8,
) -> AgentRunResult:
    client = _client()
    tool_defs = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in tools
    ]
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    result = AgentRunResult()
    seq = 0

    for _ in range(max_turns):
        resp = _create(
            client,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=tool_defs,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            messages=messages,
        )
        result.turns += 1

        if resp.stop_reason == "refusal":
            result.stopped_because = "refusal"
            result.steps.append(
                ArmTrajectoryStep(seq=seq, kind="agent_msg", text="[model declined the request]")
            )
            break

        text_parts = [b.text for b in resp.content if b.type == "text" and b.text.strip()]
        tool_uses = [b for b in resp.content if b.type == "tool_use"]

        if text_parts:
            result.steps.append(
                ArmTrajectoryStep(seq=seq, kind="model_turn", text=" ".join(text_parts).strip())
            )
            seq += 1

        if not tool_uses:
            if text_parts:
                result.steps[-1] = ArmTrajectoryStep(
                    seq=result.steps[-1].seq, kind="agent_msg", text=result.steps[-1].text
                )
            result.stopped_because = resp.stop_reason or "end_turn"
            break

        # Echo the assistant turn back verbatim, thinking blocks included.
        messages.append({"role": "assistant", "content": resp.content})

        tool_results = []
        aborted = False
        for tu in tool_uses:
            args = tu.input if isinstance(tu.input, dict) else json.loads(tu.input)
            result.steps.append(
                ArmTrajectoryStep(seq=seq, kind="tool_call", tool_name=tu.name, args=args)
            )
            seq += 1
            try:
                out = host.call(tu.name, args)
            except UnknownEffectError as e:
                result.aborted_by_unknown_effect = True
                result.stopped_because = "unknown_effect"
                result.steps.append(
                    ArmTrajectoryStep(seq=seq, kind="agent_msg", text=f"run aborted: {e}")
                )
                seq += 1
                aborted = True
                break
            result.steps.append(
                ArmTrajectoryStep(seq=seq, kind="tool_result", tool_name=tu.name, result=out)
            )
            seq += 1
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(out),
                }
            )
        if aborted:
            break
        messages.append({"role": "user", "content": tool_results})
    else:
        result.stopped_because = "max_turns"

    return result
