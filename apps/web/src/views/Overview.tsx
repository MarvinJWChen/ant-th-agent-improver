import { useNavigate } from "react-router-dom";
import {
  Badge, Button, Card, EmptyState, KeyValue, SectionHeading, Spinner, StatTile, Table,
} from "../components";
import { api, fmtMs, pct } from "../lib/api";
import type { AgentOverview, Health, ToolDef, TraceSummary } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";

const EFFECT_TONE: Record<string, "ok" | "warn" | "danger" | "neutral"> = {
  read: "ok",
  shadow_write: "warn",
  external: "danger",
  unknown: "neutral",
};

const EFFECT_NOTE: Record<string, string> = {
  read: "reads state only",
  shadow_write: "writes internal state",
  external: "leaves our boundary — money or customer contact",
  unknown: "undeclared",
};

export function Overview() {
  const nav = useNavigate();
  const journey = useJourney();
  const { data, error, loading } = useAsync<AgentOverview>(() => api.agent(), []);
  const health = useAsync<Health>(() => api.health(), []);
  const traces = useAsync<TraceSummary[]>(() => api.traces(8), []);
  const discover = useAction<unknown>();

  if (loading) return <Loading label="Loading agent" />;
  if (error || !data) return <Failed message={error ?? "no data"} />;

  const c = data.corpus;
  const notResolved = c.total_traces - (c.outcome_counts.resolved ?? 0);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-6">
      <SectionHeading
        as="h1"
        title={`Monitoring ${data.agent_name}`}
        subtitle="A managed customer-support refund agent, and every production trace it has produced."
        right={
          <Badge tone="accent" mono dot>
            {data.active_config.version} active
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Production traces" value={c.total_traces.toLocaleString()} sublabel={`${c.total_events.toLocaleString()} recorded events`} />
        <StatTile label="Self-resolved" value={pct(c.resolution_rate)} sublabel={`${notResolved} needed a human or were dropped`} />
        <StatTile label="Escalation rate" value={pct(c.escalation_rate)} sublabel={`${c.outcome_counts.escalated ?? 0} escalations`} />
        <StatTile label="p95 handling time" value={fmtMs(c.p95_duration_ms)} sublabel={`p50 ${fmtMs(c.p50_duration_ms)}`} />
      </div>

      <Card
        title="Why this needs looking at"
        subtitle="Aggregate health looks acceptable. That is exactly the problem — recurring failures hide inside a healthy-looking average."
      >
        <p className="text-sm leading-relaxed text-secondary">
          {pct(c.resolution_rate, 0)} of {c.total_traces.toLocaleString()} conversations resolved without a
          human. Nothing in this summary tells you whether the {notResolved} that did not are the same
          failure repeating, or {notResolved} unrelated one-offs — and nothing tells you whether any of the
          resolved ones quietly refunded a customer twice.
        </p>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Agent configuration" subtitle={`${data.active_config.model} · config hash ${data.active_config.config_hash.slice(0, 12)}…`}>
          <KeyValue
            items={[
              { key: "version", label: "version", value: data.active_config.version, mono: true },
              { key: "status", label: "status", value: data.active_config.status },
              { key: "created", label: "created", value: data.active_config.created_at, mono: true },
            ]}
          />
          <div className="mt-3 rounded border border-hairline bg-surface-0 p-3">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">system prompt</div>
            <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-secondary">
              {data.active_config.system_prompt}
            </p>
          </div>
        </Card>

        <Card
          title="Tool surface"
          subtitle="Each tool declares its blast radius. Replay refuses to execute anything not declared here."
          noPadding
        >
          <Table<ToolDef>
            columns={[
              { key: "name", header: "Tool", render: (t) => <span className="font-mono text-xs">{t.name}</span> },
              {
                key: "effect_class",
                header: "Effect",
                render: (t) => (
                  <Badge tone={EFFECT_TONE[t.effect_class] ?? "neutral"} mono>
                    {t.effect_class}
                  </Badge>
                ),
              },
              { key: "note", header: "", render: (t) => <span className="text-xs text-muted">{EFFECT_NOTE[t.effect_class]}</span> },
            ]}
            rows={data.active_config.tools}
            rowKey={(t) => t.name}
          />
        </Card>
      </div>

      <Card title="Recent traces" subtitle="A sample of the corpus in its raw form." noPadding>
        <Table<TraceSummary>
          columns={[
            { key: "trace_id", header: "Trace", render: (t) => <span className="font-mono text-xs">{t.trace_id}</span> },
            { key: "intent", header: "Intent", render: (t) => <span className="text-xs">{t.intent}</span> },
            { key: "turns", header: "Turns", numeric: true, render: (t) => <span className="font-mono text-xs">{t.turns}</span> },
            { key: "duration_ms", header: "Duration", numeric: true, render: (t) => <span className="font-mono text-xs">{fmtMs(t.duration_ms)}</span> },
            {
              key: "outcome",
              header: "Outcome",
              render: (t) => (
                <Badge tone={t.outcome === "resolved" ? "ok" : t.outcome === "escalated" ? "warn" : "neutral"}>
                  {t.outcome}
                </Badge>
              ),
            },
          ]}
          rows={traces.data ?? []}
          rowKey={(t) => t.trace_id}
          emptyMessage={traces.loading ? "Loading…" : "No traces"}
        />
      </Card>

      <div className="flex flex-col items-start gap-2 border-t border-hairline pt-5">
        <Button
          size="md"
          loading={discover.pending === "run"}
          onClick={async () => {
            const res = await discover.run("run", () => api.runDiscovery());
            if (res) {
              journey.mark({ discovered: true });
              nav("/discovery");
            }
          }}
        >
          Discover failure patterns →
        </Button>
        <p className="text-xs text-muted">
          Runs the detection pipeline over all {c.total_traces.toLocaleString()} traces now: generic
          featurisation, anomaly scoring, and clustering. Nothing is precomputed.
        </p>
        {discover.error && <p className="text-xs text-danger">{discover.error}</p>}
        {health.data && (
          <p className="pt-1 font-mono text-[11px] text-muted">
            subsystems:{" "}
            {Object.entries(health.data.subsystems)
              .map(([k, v]) => `${k}=${v}`)
              .join("  ")}
            {"  live_inference="}
            {health.data.live_available ? "available" : "no-key"}
          </p>
        )}
      </div>
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-16 text-sm text-muted">
      <Spinner /> {label}…
    </div>
  );
}

export function Failed({ message }: { message: string }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <EmptyState title="Request failed" description={message} />
    </div>
  );
}

export default Overview;
