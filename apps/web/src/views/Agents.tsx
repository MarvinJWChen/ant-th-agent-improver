import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, SectionHeading, StatTile } from "../components";
import { api, pct } from "../lib/api";
import type { AgentOverview, Health } from "../lib/api";
import { useAsync, useJourney } from "../lib/state";
import { DEFAULT_AGENT_ID } from "../lib/journey";
import { Failed, Loading } from "./Overview";

/**
 * Step 1 — the managed agents this deployment is watching.
 *
 * Deliberately a click rather than a redirect: it establishes that the refund
 * agent is a pre-existing, already-running managed agent whose production
 * traffic we are observing, not something this tool spun up for the demo.
 */
export function Agents() {
  const nav = useNavigate();
  const journey = useJourney();
  const { data, error, loading } = useAsync<AgentOverview>(() => api.agent(), []);
  const health = useAsync<Health>(() => api.health(), []);

  if (loading) return <Loading label="Loading managed agents" />;
  if (error || !data) return <Failed message={error ?? "no data"} />;

  const open = () => {
    journey.mark({ activePatternId: undefined });
    nav(`/agents/${DEFAULT_AGENT_ID}`);
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-12 space-y-8">
      <SectionHeading
        as="h1"
        title="Managed agents"
        subtitle="Agents running in production, with their traces streaming into this workspace. Open one to review how it has actually been behaving."
      />

      <Card
        title={
          <span className="flex items-center gap-3">
            <span className="font-mono">{data.agent_name}</span>
            <Badge tone="ok" dot>
              running
            </Badge>
          </span>
        }
        subtitle={`${data.active_config.model} · configuration ${data.active_config.version} · ${data.active_config.tools.length} tools`}
        right={
          <Button size="lg" onClick={open}>
            Open agent →
          </Button>
        }
        footer={
          <p className="text-muted">
            Customer-support refund agent. Handles refund requests, status enquiries,
            cancellations and order questions for an online retailer.
          </p>
        }
      >
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatTile
            label="Traces observed"
            value={data.corpus.total_traces.toLocaleString()}
            sublabel={`${data.corpus.window_start.slice(0, 10)} → ${data.corpus.window_end.slice(0, 10)}`}
          />
          <StatTile label="Self-resolved" value={pct(data.corpus.resolution_rate, 0)} />
          <StatTile label="Escalated" value={pct(data.corpus.escalation_rate, 0)} />
          <StatTile
            label="Live inference"
            value={health.data?.live_available ? "enabled" : "cached only"}
            sublabel={health.data?.live_available ? "API key configured" : "no API key on this deployment"}
          />
        </div>
      </Card>

      <p className="text-muted">
        This workspace manages one agent. Everything below the fold of that agent — its traces,
        the patterns discovered in them, and any configuration change promoted — is computed from
        its own recorded production traffic.
      </p>
    </div>
  );
}

export default Agents;
