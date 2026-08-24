import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, SectionHeading, StatTile, Table } from "../components";
import { api, fmtMs, pct } from "../lib/api";
import type { AgentOverview, Health, ToolDef } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { Failed, Loading } from "../lib/ui";

export { Failed, Loading };

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
  const discover = useAction<unknown>();

  if (loading) return <Loading label="Loading agent" />;
  if (error || !data) return <Failed message={error ?? "no data"} />;

  const c = data.corpus;
  const notResolved = c.total_traces - (c.outcome_counts.resolved ?? 0);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <SectionHeading
        as="h1"
        title={data.agent_name}
        subtitle="Every conversation this agent has handled in production, as recorded."
        right={
          <Badge tone="accent" mono dot>
            {data.active_config.version}
          </Badge>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile
          label="Production traces"
          value={c.total_traces.toLocaleString()}
          sublabel={`${c.total_events.toLocaleString()} recorded events`}
        />
        <StatTile label="Self-resolved" value={pct(c.resolution_rate, 0)} />
        <StatTile
          label="Needed a human"
          value={String(c.outcome_counts.escalated ?? 0)}
          sublabel={`${pct(c.escalation_rate, 0)} of traffic`}
        />
        <StatTile
          label="p95 handling time"
          value={fmtMs(c.p95_duration_ms)}
          sublabel={`p50 ${fmtMs(c.p50_duration_ms)}`}
        />
      </div>

      <Card title="Why this needs looking at">
        <p className="leading-relaxed text-secondary">
          {pct(c.resolution_rate, 0)} of conversations resolved without a human, which looks
          healthy. Nothing in that number tells you whether the {notResolved} that did not are one
          bug repeating or {notResolved} unrelated one-offs — or whether any of the resolved ones
          quietly refunded a customer twice.
        </p>
      </Card>

      <Card
        title="Tool surface"
        subtitle="Each tool declares its blast radius. Replay refuses to execute anything not declared here."
        noPadding
      >
        <Table<ToolDef>
          columns={[
            {
              key: "name",
              header: "Tool",
              render: (t) => <span className="font-mono">{t.name}</span>,
            },
            {
              key: "effect_class",
              header: "Effect",
              render: (t) => (
                <Badge tone={EFFECT_TONE[t.effect_class] ?? "neutral"} mono>
                  {t.effect_class}
                </Badge>
              ),
            },
            {
              key: "note",
              header: "",
              render: (t) => <span className="text-muted">{EFFECT_NOTE[t.effect_class]}</span>,
            },
          ]}
          rows={data.active_config.tools}
          rowKey={(t) => t.name}
        />
      </Card>

      <div className="flex flex-col items-start gap-3 border-t border-hairline pt-8">
        <Button
          size="lg"
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
        <p className="text-muted">
          Runs detection over all {c.total_traces.toLocaleString()} traces now — featurisation,
          anomaly scoring and clustering. Nothing is precomputed.
        </p>
        {discover.error && <p className="text-danger">{discover.error}</p>}
        {health.data && (
          <p className="pt-2 font-mono text-muted">
            {Object.entries(health.data.subsystems)
              .map(([k, v]) => `${k}=${v}`)
              .join("  ")}
          </p>
        )}
      </div>
    </div>
  );
}

export default Overview;
