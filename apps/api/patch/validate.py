"""The candidate-edit boundary.

A generated patch may rewrite the system prompt and the description of an
existing tool. That is the entire permitted surface. It may not add, remove, or
rename a tool, and it may not touch an input schema — because the moment a patch
can change the tool surface, the effect registry that replay depends on stops
describing what the agent can actually do.

Rejection is not advisory. A patch outside the boundary never becomes a
candidate config, so it can never reach the gate.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from apps.api.llm.capture import sha


class PatchOutOfBounds(ValueError):
    pass


@dataclass
class BoundaryReport:
    within_bounds: bool
    changes: list[str]
    violations: list[str]


def apply_patch(
    base_config: dict[str, Any],
    system_prompt_after: str,
    tool_description_edits: list[dict[str, str]],
) -> tuple[dict[str, Any], BoundaryReport]:
    changes: list[str] = []
    violations: list[str] = []

    tools_by_name = {t["name"]: t for t in base_config["tools"]}
    new_tools = copy.deepcopy(base_config["tools"])
    index = {t["name"]: i for i, t in enumerate(new_tools)}

    for edit in tool_description_edits:
        name = edit.get("tool_name", "")
        after = edit.get("after", "")
        if name not in tools_by_name:
            violations.append(
                f"tools[{name}]: patch targets a tool that does not exist in the base config"
            )
            continue
        if not after.strip():
            violations.append(f"tools[{name}].description: empty replacement rejected")
            continue
        before = tools_by_name[name]["description"]
        if before != after:
            new_tools[index[name]]["description"] = after
            changes.append(f"tools[{name}].description: changed")

    if system_prompt_after.strip() and system_prompt_after != base_config["system_prompt"]:
        changes.append("system_prompt: changed")
    elif not system_prompt_after.strip():
        violations.append("system_prompt: empty replacement rejected")

    # Structural invariants: nothing but descriptions may have moved.
    before_names = [t["name"] for t in base_config["tools"]]
    after_names = [t["name"] for t in new_tools]
    if before_names != after_names:
        violations.append("tool set changed: names added, removed, or reordered")
    for b, a in zip(base_config["tools"], new_tools):
        if json.dumps(b["input_schema"], sort_keys=True) != json.dumps(
            a["input_schema"], sort_keys=True
        ):
            violations.append(f"tools[{b['name']}].input_schema changed")

    if not changes and not violations:
        violations.append("patch is a no-op: nothing changed")

    report = BoundaryReport(
        within_bounds=not violations, changes=changes, violations=violations
    )
    patched = {
        **base_config,
        "system_prompt": system_prompt_after if system_prompt_after.strip() else base_config["system_prompt"],
        "tools": new_tools,
    }
    return patched, report


def config_hash(model: str, system_prompt: str, tools: list[dict[str, Any]]) -> str:
    return sha(
        {
            "model": model,
            "system_prompt": system_prompt,
            "tools": [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                for t in tools
            ],
        }
    )


def tools_hash(tools: list[dict[str, Any]]) -> str:
    return sha([{"name": t["name"], "description": t["description"]} for t in tools])
