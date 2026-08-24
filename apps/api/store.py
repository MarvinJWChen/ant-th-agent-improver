"""Read-only access to the seeded corpus and the agent-config registry.

Deliberately narrow: this module knows about traces, events, and configs. It has
no path to var/hidden_labels.db and never will — those labels exist only for
offline validation (see SCHEMA.md).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from functools import lru_cache
from typing import Any

from apps.api import paths
from apps.api.contracts import (
    AgentConfigOut,
    CorpusStats,
    ToolDef,
    TraceDetail,
    TraceEvent,
    TraceSummary,
)
from apps.api.tool_registry import effect_class


def _conn(path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def corpus_available() -> bool:
    return paths.TRACES_DB.exists() and paths.CONFIGS_DB.exists()


def _loads(v: str | None) -> dict[str, Any] | None:
    if not v:
        return None
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------ configs


def get_config(version: str) -> AgentConfigOut:
    with _conn(paths.CONFIGS_DB) as c:
        row = c.execute(
            "SELECT * FROM agent_configs WHERE version = ?", (version,)
        ).fetchone()
    if row is None:
        raise KeyError(f"no such config version: {version}")
    return _config_from_row(row)


def active_config() -> AgentConfigOut:
    with _conn(paths.CONFIGS_DB) as c:
        row = c.execute(
            "SELECT * FROM agent_configs WHERE status = 'active' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise KeyError("no active agent config")
    return _config_from_row(row)


def list_configs() -> list[AgentConfigOut]:
    with _conn(paths.CONFIGS_DB) as c:
        rows = c.execute(
            "SELECT * FROM agent_configs ORDER BY created_at"
        ).fetchall()
    return [_config_from_row(r) for r in rows]


def _config_from_row(row: sqlite3.Row) -> AgentConfigOut:
    tools_raw = json.loads(row["tools_json"])
    tools = [
        ToolDef(
            name=t["name"],
            description=t["description"],
            input_schema=t.get("input_schema", {}),
            effect_class=effect_class(t["name"]),
        )
        for t in tools_raw
    ]
    return AgentConfigOut(
        version=row["version"],
        created_at=row["created_at"],
        model=row["model"],
        system_prompt=row["system_prompt"],
        tools=tools,
        config_hash=row["config_hash"],
        status=row["status"],
        parent_version=row["parent_version"],
        notes=row["notes"],
    )


def write_config(
    *,
    version: str,
    created_at: str,
    model: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    config_hash: str,
    status: str,
    parent_version: str | None,
    notes: str | None,
) -> None:
    with sqlite3.connect(paths.CONFIGS_DB) as c:
        c.execute(
            "INSERT OR REPLACE INTO agent_configs(version, created_at, model, "
            "system_prompt, tools_json, config_hash, status, parent_version, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                version,
                created_at,
                model,
                system_prompt,
                json.dumps(tools),
                config_hash,
                status,
                parent_version,
                notes,
            ),
        )


def set_status(version: str, status: str) -> None:
    with sqlite3.connect(paths.CONFIGS_DB) as c:
        c.execute("UPDATE agent_configs SET status = ? WHERE version = ?", (status, version))


def demote_active() -> None:
    with sqlite3.connect(paths.CONFIGS_DB) as c:
        c.execute("UPDATE agent_configs SET status = 'archived' WHERE status = 'active'")


# ------------------------------------------------------------------ traces


def _trace_summary(row: sqlite3.Row) -> TraceSummary:
    return TraceSummary(
        trace_id=row["trace_id"],
        ts=row["ts"],
        customer_id=row["customer_id"],
        order_id=row["order_id"],
        intent=row["intent"],
        duration_ms=row["duration_ms"],
        turns=row["turns"],
        outcome=row["outcome"],
        summary=row["summary"],
    )


def list_traces(limit: int = 50, offset: int = 0, outcome: str | None = None) -> list[TraceSummary]:
    q = "SELECT * FROM traces"
    args: list[Any] = []
    if outcome:
        q += " WHERE outcome = ?"
        args.append(outcome)
    q += " ORDER BY ts DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with _conn(paths.TRACES_DB) as c:
        rows = c.execute(q, args).fetchall()
    return [_trace_summary(r) for r in rows]


def get_trace(trace_id: str) -> TraceDetail:
    with _conn(paths.TRACES_DB) as c:
        row = c.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
        if row is None:
            raise KeyError(f"no such trace: {trace_id}")
        evs = c.execute(
            "SELECT * FROM events WHERE trace_id = ? ORDER BY seq", (trace_id,)
        ).fetchall()
    return TraceDetail(
        **_trace_summary(row).model_dump(),
        config_version=row["config_version"],
        events=[
            TraceEvent(
                seq=e["seq"],
                type=e["type"],
                tool_name=e["tool_name"],
                args=_loads(e["args_json"]),
                result=_loads(e["result_json"]),
                latency_ms=e["latency_ms"] or 0,
                error=e["error"],
                content=e["content"],
            )
            for e in evs
        ],
    )


def get_traces(trace_ids: list[str]) -> dict[str, TraceDetail]:
    return {tid: get_trace(tid) for tid in trace_ids}


def all_trace_ids() -> list[str]:
    with _conn(paths.TRACES_DB) as c:
        return [r[0] for r in c.execute("SELECT trace_id FROM traces ORDER BY trace_id")]


@lru_cache(maxsize=1)
def corpus_stats() -> CorpusStats:
    with _conn(paths.TRACES_DB) as c:
        total = c.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        events = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        lo, hi = c.execute("SELECT MIN(ts), MAX(ts) FROM traces").fetchone()
        outcomes = dict(c.execute("SELECT outcome, COUNT(*) FROM traces GROUP BY outcome"))
        intents = dict(c.execute("SELECT intent, COUNT(*) FROM traces GROUP BY intent"))
        durs = [r[0] for r in c.execute("SELECT duration_ms FROM traces ORDER BY duration_ms")]
    p50 = durs[len(durs) // 2] if durs else 0
    p95 = durs[int(len(durs) * 0.95)] if durs else 0
    esc = outcomes.get("escalated", 0)
    res = outcomes.get("resolved", 0)
    return CorpusStats(
        total_traces=total,
        total_events=events,
        window_start=lo or "",
        window_end=hi or "",
        outcome_counts=outcomes,
        intent_counts=intents,
        p50_duration_ms=p50,
        p95_duration_ms=p95,
        escalation_rate=round(esc / total, 4) if total else 0.0,
        resolution_rate=round(res / total, 4) if total else 0.0,
    )


@lru_cache(maxsize=1)
def corpus_hash() -> str:
    """Identifies the exact corpus a capture was produced against."""
    h = hashlib.sha256()
    with _conn(paths.TRACES_DB) as c:
        for row in c.execute("SELECT trace_id, ts, outcome, turns, duration_ms FROM traces ORDER BY trace_id"):
            h.update("|".join(str(x) for x in row).encode())
    return h.hexdigest()
