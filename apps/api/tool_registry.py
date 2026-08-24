"""Canonical effect classification for the refund agent's tool surface.

This registry is the *only* place a tool's blast radius is declared, and it is
what makes replay fail-closed: a tool the registry does not know about cannot be
executed under replay at all. Config patches may reword a tool description, but
they can never introduce a tool or change its effect class (see patch/validate).
"""
from __future__ import annotations

from typing import Literal

EffectClass = Literal["read", "shadow_write", "external", "unknown"]

# tool name -> (effect_class, target_field, human note)
REGISTRY: dict[str, tuple[EffectClass, str, str]] = {
    "order_lookup": ("read", "order_id", "Reads the orders table on the cloned world."),
    "refund_status": ("read", "order_id", "Reads the refunds table on the cloned world."),
    "refund_execute": (
        "external",
        "order_id",
        "Moves money via the payment processor. Never executed under replay; "
        "recorded as SHADOWED and reflected only in the clone.",
    ),
    "send_email": (
        "external",
        "customer_id",
        "Sends mail to a real customer. Never executed under replay; recorded as "
        "SHADOWED and reflected only in the clone.",
    ),
    "escalate_to_human": (
        "shadow_write",
        "order_id",
        "Creates a support escalation. Written to the clone only.",
    ),
}


def effect_class(tool_name: str) -> EffectClass:
    entry = REGISTRY.get(tool_name)
    return entry[0] if entry else "unknown"


def target_of(tool_name: str, args: dict) -> str:
    entry = REGISTRY.get(tool_name)
    if not entry:
        return "?"
    return str(args.get(entry[1], "?"))


def note_for(tool_name: str) -> str:
    entry = REGISTRY.get(tool_name)
    return entry[2] if entry else "Unregistered tool — effect unknown."


def is_known(tool_name: str) -> bool:
    return tool_name in REGISTRY
