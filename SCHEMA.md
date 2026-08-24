# Data contract (authoritative — do not deviate)

All SQLite. Paths come from `apps/api/paths.py`. Timestamps are ISO-8601 UTC
strings (`2026-07-14T09:31:02Z`). All generation is deterministic: seed 1337.

## `var/traces.db`

```sql
CREATE TABLE traces(
  trace_id       TEXT PRIMARY KEY,   -- "tr_000001"
  ts             TEXT NOT NULL,      -- trace start
  customer_id    TEXT NOT NULL,      -- "cus_0412"
  order_id       TEXT NOT NULL,      -- "ord_10233"
  intent         TEXT NOT NULL,      -- refund_request|refund_status_inquiry|order_question|cancel_request
  config_version TEXT NOT NULL,      -- "v1"
  duration_ms    INTEGER NOT NULL,
  turns          INTEGER NOT NULL,
  outcome        TEXT NOT NULL,      -- resolved|escalated|abandoned
  summary        TEXT NOT NULL       -- one-line human summary
);
CREATE TABLE events(
  trace_id   TEXT NOT NULL,
  seq        INTEGER NOT NULL,
  type       TEXT NOT NULL,   -- user_msg|model_turn|tool_call|tool_result|agent_msg|escalation
  tool_name  TEXT,            -- set on tool_call/tool_result
  args_json  TEXT,            -- JSON object, tool_call only
  result_json TEXT,           -- JSON object, tool_result only
  latency_ms INTEGER NOT NULL DEFAULT 0,
  error      TEXT,            -- e.g. "timeout" — tool_result only
  content    TEXT,            -- text for user_msg/agent_msg/model_turn
  PRIMARY KEY(trace_id, seq)
);
CREATE INDEX idx_events_trace ON events(trace_id);
```

## `var/worlds/<trace_id>.sqlite` — frozen world as of trace start

```sql
CREATE TABLE orders(
  order_id TEXT PRIMARY KEY, customer_id TEXT, amount_cents INTEGER,
  currency TEXT, placed_at TEXT, status TEXT);            -- delivered|shipped|cancelled
CREATE TABLE refunds(
  refund_id TEXT PRIMARY KEY, order_id TEXT, amount_cents INTEGER,
  state TEXT,                                              -- processing|completed|failed
  requested_at TEXT, completed_at TEXT, processor_ref TEXT);
CREATE TABLE emails(
  email_id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT,
  template TEXT, sent_at TEXT, idempotency_key TEXT);      -- refund_confirmation|refund_delay_notice
CREATE TABLE escalations(
  escalation_id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT,
  reason TEXT, created_at TEXT, refund_state_at_escalation TEXT);
CREATE TABLE world_meta(key TEXT PRIMARY KEY, value TEXT);
-- world_meta keys: trace_id, frozen_at, sla_hours, now (the simulated clock)
```

## `var/hidden_labels.db` — OFFLINE VALIDATION ONLY

```sql
CREATE TABLE hidden_labels(trace_id TEXT PRIMARY KEY, family TEXT);
-- family: healthy | F1_double_refund | F2_duplicate_confirmation | F3_premature_escalation
```

**No module under `apps/api/` may import, open, or reference this file or the
string `hidden_labels`.** Only `scripts/` may. This is asserted in validation.

## `var/configs.db`

```sql
CREATE TABLE agent_configs(
  version TEXT PRIMARY KEY,          -- "v1" | "v2-candidate-a" | "v2"
  created_at TEXT, model TEXT,
  system_prompt TEXT, tools_json TEXT,
  config_hash TEXT,                  -- sha256 over canonical {model,system_prompt,tools}
  status TEXT,                       -- active|candidate|blocked|archived
  parent_version TEXT, notes TEXT
);
```

## Tool surface of the refund agent (v1)

| tool | effect_class | args | notes |
|---|---|---|---|
| `order_lookup` | read | `{order_id}` | returns order row |
| `refund_status` | read | `{order_id}` | **v1 description is ambiguous on purpose** |
| `refund_execute` | shadow_write + external | `{order_id, amount_cents}` | payment side effect — never really executed |
| `send_email` | external | `{customer_id, template, order_id, idempotency_key?}` | v1 has no idempotency key |
| `escalate_to_human` | shadow_write | `{order_id, reason}` | |
