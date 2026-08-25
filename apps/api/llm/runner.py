"""The single entry point for every model-dependent output.

Live and cached mode differ in exactly one place: whether the transport call
happens or its previously recorded result is returned. Prompt construction,
schema, versioning, and validation are shared, which is what makes a capture a
recording of this code path rather than a fixture that resembles one.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from apps.api.contracts import Provenance
from apps.api.llm import capture as cap
from apps.api.llm.tasks import TASKS

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
EFFORT = "high"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class NoCaptureAvailable(RuntimeError):
    pass


class LiveUnavailable(RuntimeError):
    pass


class SchemaViolation(RuntimeError):
    pass


def live_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def validate(obj: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Enough JSON-Schema to catch a malformed model response, no dependency."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            raise SchemaViolation(f"{path}: expected object, got {type(obj).__name__}")
        for k in schema.get("required", []):
            if k not in obj:
                raise SchemaViolation(f"{path}: missing required key {k!r}")
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                validate(obj[k], sub, f"{path}.{k}")
    elif t == "array":
        if not isinstance(obj, list):
            raise SchemaViolation(f"{path}: expected array, got {type(obj).__name__}")
        item = schema.get("items")
        if item:
            for i, v in enumerate(obj):
                validate(v, item, f"{path}[{i}]")
    elif t == "string":
        if not isinstance(obj, str):
            raise SchemaViolation(f"{path}: expected string")
        if "enum" in schema and obj not in schema["enum"]:
            raise SchemaViolation(f"{path}: {obj!r} not in {schema['enum']}")
    elif t == "boolean" and not isinstance(obj, bool):
        raise SchemaViolation(f"{path}: expected boolean")
    elif t == "integer" and not isinstance(obj, int):
        raise SchemaViolation(f"{path}: expected integer")


def build_key(
    task_name: str,
    inputs: dict[str, Any],
    *,
    agent_config_hash: str,
    tools_hash: str,
    corpus_hash: str,
    world_hash: str = "n/a",
    loop_version: str = "n/a",
) -> tuple[cap.ProvenanceKey, str, str]:
    task = TASKS[task_name]
    system, user = task.build(inputs)
    key = cap.ProvenanceKey(
        task=task.name,
        task_version=task.version,
        model=task.model or MODEL,
        prompt_hash=cap.sha_text(system + "\x00" + user),
        inputs_hash=cap.sha(inputs),
        output_schema_hash=cap.sha(task.schema),
        agent_config_hash=agent_config_hash,
        tools_hash=tools_hash,
        corpus_hash=corpus_hash,
        world_hash=world_hash,
        loop_version=loop_version,
    )
    return key, system, user


def _call_live(
    system: str,
    user: str,
    schema: dict[str, Any],
    model: str = MODEL,
    effort: str = EFFORT,
) -> tuple[dict[str, Any], int]:
    if not live_available():
        raise LiveUnavailable("ANTHROPIC_API_KEY is not set")
    import anthropic  # lazy: cached mode must not require the SDK to be configured

    client = anthropic.Anthropic()
    kw = dict(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    t0 = time.time()
    try:
        resp = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kw)
    except Exception as e:  # noqa: BLE001 - the beta may not be enabled on this org
        low = str(e).lower()
        if "beta" not in low and "fallback" not in low and "unexpected" not in low:
            raise
        resp = client.messages.create(**kw)
    latency = int((time.time() - t0) * 1000)

    if getattr(resp, "stop_reason", None) == "refusal":
        raise SchemaViolation("model declined the request")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), latency


def run(
    task_name: str,
    inputs: dict[str, Any],
    mode: str,
    *,
    agent_config_hash: str,
    tools_hash: str,
    corpus_hash: str,
    world_hash: str = "n/a",
    loop_version: str = "n/a",
) -> tuple[dict[str, Any], Provenance]:
    task = TASKS[task_name]
    key, system, user = build_key(
        task_name,
        inputs,
        agent_config_hash=agent_config_hash,
        tools_hash=tools_hash,
        corpus_hash=corpus_hash,
        world_hash=world_hash,
        loop_version=loop_version,
    )

    if mode == "live":
        output, latency = _call_live(
            system, user, task.schema, task.model or MODEL, task.effort or EFFORT
        )
        validate(output, task.schema)
        cap.save(key, output, notes="Captured from a live run triggered in the browser.")
        return output, Provenance(
            mode="live",
            task=task.name,
            task_version=task.version,
            model=task.model or MODEL,
            created_at=cap.datetime.now(cap.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            verified=True,
            stale_reason=None,
            hashes=key.as_dict(),
            expected_hashes=None,
            latency_ms=latency,
        )

    found, verified, reason, mismatches = cap.resolve(key)
    if found is None:
        raise NoCaptureAvailable(reason)
    validate(found.output, task.schema)
    return found.output, Provenance(
        mode="captured",
        task=task.name,
        task_version=task.version,
        model=found.key.get("model", task.model or MODEL),
        created_at=found.created_at,
        verified=verified,
        stale_reason=None if verified else reason,
        hashes=found.key,
        expected_hashes=key.as_dict() if not verified else None,
        latency_ms=None,
    )
