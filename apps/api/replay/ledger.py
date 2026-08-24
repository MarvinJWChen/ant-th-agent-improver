"""The Effect Ledger.

Every attempt an arm makes to affect the world is recorded here before anything
happens, including the attempts we refuse. Metrics and the promotion gate read
this ledger rather than the agent's own account of what it did, so a run cannot
claim an effect it did not record or hide one it did.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from apps.api.contracts import LedgerRow


class UnknownEffectError(RuntimeError):
    """Raised when an arm calls a tool whose blast radius is not declared.

    Fail-closed: we cannot bound what an unregistered tool would do, so the run
    is aborted rather than allowed to continue on an assumption.
    """


def args_digest(args: dict) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


@dataclass
class Ledger:
    run_id: str
    arm: str
    trace_id: str
    rows: list[LedgerRow] = field(default_factory=list)

    def record(
        self,
        *,
        tool: str,
        effect_class: str,
        target: str,
        args: dict,
        disposition: str,
        note: str | None = None,
    ) -> LedgerRow:
        row = LedgerRow(
            seq=len(self.rows),
            tool=tool,
            effect_class=effect_class,  # type: ignore[arg-type]
            target=target,
            args_digest=args_digest(args),
            disposition=disposition,  # type: ignore[arg-type]
            external=effect_class == "external",
            note=note,
        )
        self.rows.append(row)
        return row

    @property
    def unsafe_effects(self) -> int:
        return sum(1 for r in self.rows if r.disposition == "BLOCKED_UNKNOWN_EFFECT")

    @property
    def external_calls_executed(self) -> int:
        """Always zero by construction: external effects are only ever shadowed.

        Computed rather than asserted so the number on screen is measured, not
        claimed.
        """
        return sum(1 for r in self.rows if r.external and r.disposition == "APPLIED_TO_CLONE")

    @property
    def shadowed(self) -> int:
        return sum(1 for r in self.rows if r.disposition == "SHADOWED")

    def dump(self) -> list[dict]:
        return [r.model_dump() for r in self.rows]
