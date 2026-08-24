"""Provenance-validated captures.

A capture is only allowed to stand in for a live model call if we can still show
it came from one — the same task at the same version, the same model, the same
prompt bytes, against the same agent config, tool surface, corpus, and frozen
world. Every one of those is hashed into the envelope at capture time and
recomputed at load time.

If any of them has moved, the capture is stale. Stale captures may still be
displayed (clearly marked), but they can never satisfy the promotion gate. That
is the whole point: cached demo mode must not become a way to promote a patch on
evidence that no longer applies.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.api import paths

ENVELOPE_VERSION = 2


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class ProvenanceKey:
    """Everything a capture's validity depends on."""

    task: str
    task_version: str
    model: str
    prompt_hash: str
    inputs_hash: str
    output_schema_hash: str
    agent_config_hash: str
    tools_hash: str
    corpus_hash: str
    world_hash: str = "n/a"
    loop_version: str = "n/a"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def capture_id(self) -> str:
        return sha(self.as_dict())[:20]


@dataclass
class Capture:
    envelope_version: int
    capture_id: str
    created_at: str
    key: dict[str, str]
    output: Any
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class StaleCapture(RuntimeError):
    def __init__(self, reason: str, mismatches: dict[str, tuple[str, str]]):
        super().__init__(reason)
        self.reason = reason
        self.mismatches = mismatches


def _dir(task: str) -> Path:
    d = paths.CAPTURES / task
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(key: ProvenanceKey, output: Any, notes: str = "", extra: dict | None = None) -> Path:
    cap = Capture(
        envelope_version=ENVELOPE_VERSION,
        capture_id=key.capture_id,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        key=key.as_dict(),
        output=output,
        notes=notes,
        extra=extra or {},
    )
    path = _dir(key.task) / f"{key.capture_id}.json"
    path.write_text(json.dumps(asdict(cap), indent=2, ensure_ascii=False))
    return path


def load_exact(key: ProvenanceKey) -> Capture | None:
    path = _dir(key.task) / f"{key.capture_id}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return Capture(**raw)


def _all_for_task(task: str) -> list[Capture]:
    out = []
    for p in sorted(_dir(task).glob("*.json")):
        try:
            out.append(Capture(**json.loads(p.read_text())))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def diff_key(expected: ProvenanceKey, found: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Which provenance fields moved, and from what to what."""
    exp = expected.as_dict()
    return {
        k: (str(found.get(k, "<missing>")), v)
        for k, v in exp.items()
        if str(found.get(k, "<missing>")) != v
    }


def resolve(key: ProvenanceKey) -> tuple[Capture | None, bool, str, dict[str, tuple[str, str]]]:
    """Find the capture for this key.

    Returns (capture, verified, human_reason, mismatches). A capture is returned
    unverified when the closest match for this task disagrees on some provenance
    field — useful to show on screen, never sufficient to promote.
    """
    exact = load_exact(key)
    if exact is not None:
        return exact, True, "Provenance verified: capture matches this exact execution.", {}

    candidates = _all_for_task(key.task)
    if not candidates:
        return None, False, f"No capture exists for task {key.task!r}.", {}

    scored = []
    for c in candidates:
        mism = diff_key(key, c.key)
        scored.append((len(mism), c, mism))
    scored.sort(key=lambda t: t[0])
    _, closest, mismatches = scored[0]
    fields = ", ".join(sorted(mismatches))
    return (
        closest,
        False,
        f"Capture is incompatible with the current execution — {len(mismatches)} "
        f"provenance field(s) differ: {fields}.",
        mismatches,
    )
