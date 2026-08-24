import { useNavigate } from "react-router-dom";
import {
  Badge, Button, Card, SectionHeading, StatTile, Table,
} from "../components";
import { api, fmtMs, pct } from "../lib/api";
import type { DiscoveryResult, FlaggedTrace, PatternCard } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { Failed, Loading } from "./Overview";

export function Discovery() {
  const nav = useNavigate();
  const journey = useJourney();
  const { data, error, loading, reload } = useAsync<DiscoveryResult>(() => api.discovery(), []);
  const rerun = useAction<DiscoveryResult>();

  if (loading) return <Loading label="Clustering flagged traces" />;
  if (error || !data) return <Failed message={error ?? "no data"} />;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-6">
      <SectionHeading
        as="h1"
        title="Discovered failure patterns"
        subtitle={`${data.n_flagged} of ${data.n_traces_scanned.toLocaleString()} traces were flagged by family-agnostic signals, then grouped into ${data.patterns.length} recurring behaviours.`}
        right={
          <Button
            variant="secondary"
            size="sm"
            loading={rerun.pending === "run"}
            onClick={async () => {
              await rerun.run("run", () => api.runDiscovery());
              reload();
            }}
          >
            Re-run detection
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Traces scanned" value={data.n_traces_scanned.toLocaleString()} sublabel="every trace, every run" />
        <StatTile label="Flagged" value={data.n_flagged} sublabel={`${pct(data.n_flagged / data.n_traces_scanned, 0)} of the corpus`} />
        <StatTile label="Anomaly-only finds" value={data.n_anomaly_only} sublabel="no observable signal fired" />
        <StatTile label="Cluster quality" value={data.silhouette.toFixed(2)} sublabel={`k=${data.cluster_k} chosen by silhouette`} />
      </div>

      <Card
        title="How these were found"
        subtitle="No pattern below was configured in advance. Both signals ran against the corpus on this request."
      >
        <div className="grid gap-4 text-sm md:grid-cols-2">
          <div>
            <div className="mb-1 font-medium text-primary">Observable failure signals</div>
            <p className="leading-relaxed text-secondary">
              Four generic signals — the agent didn't finish, an effect repeated at one target, an effect
              issued at a target already read as finished, a retry after an ambiguous timeout — flagged{" "}
              <span className="font-mono">{data.n_rule_flagged}</span> traces. None of them names a refund,
              an email, or an SLA, so the seeded failures have to be recovered from behaviour alone.
            </p>
          </div>
          <div>
            <div className="mb-1 font-medium text-primary">Generic anomaly model</div>
            <p className="leading-relaxed text-secondary">
              Scores every trace on incompletion, cost relative to same-intent peers, and shape
              isolation — threshold{" "}
              <span className="font-mono">{data.anomaly_threshold.toFixed(3)}</span>. It contributed{" "}
              <span className="font-mono">{data.n_anomaly_only}</span> traces no signal caught.
            </p>
          </div>
        </div>
      </Card>

      <div>
        <SectionHeading title="Recurring patterns" subtitle="Clustered from the flagged set. Investigate one to get a diagnosis." size="sm" />
        <div className="mt-3 grid gap-3">
          {data.patterns.map((p) => (
            <PatternRow
              key={p.pattern_id}
              pattern={p}
              onInvestigate={() => {
                journey.mark({ activePatternId: p.pattern_id });
                nav(`/patterns/${p.pattern_id}`);
              }}
            />
          ))}
        </div>
      </div>

      <Card title="Flagged traces" subtitle="The raw flagged set, ranked by anomaly score." noPadding>
        <Table<FlaggedTrace>
          maxHeightClassName="max-h-96"
          stickyHeader
          columns={[
            { key: "trace_id", header: "Trace", render: (f) => <span className="font-mono text-xs">{f.trace.trace_id}</span> },
            { key: "intent", header: "Intent", render: (f) => <span className="text-xs">{f.trace.intent}</span> },
            { key: "outcome", header: "Outcome", render: (f) => <span className="text-xs">{f.trace.outcome}</span> },
            { key: "duration", header: "Duration", numeric: true, render: (f) => <span className="font-mono text-xs">{fmtMs(f.trace.duration_ms)}</span> },
            { key: "score", header: "Anomaly", numeric: true, render: (f) => <span className="font-mono text-xs">{f.anomaly_score.toFixed(3)}</span> },
            {
              key: "how",
              header: "Found by",
              render: (f) =>
                f.rule_flagged ? (
                  <Badge tone="info">signal + anomaly</Badge>
                ) : (
                  <Badge tone="accent" dot>anomaly only</Badge>
                ),
            },
            { key: "cluster", header: "Pattern", render: (f) => <span className="font-mono text-xs text-muted">P{(f.cluster_id ?? 0) + 1}</span> },
          ]}
          rows={data.flagged.slice(0, 120)}
          rowKey={(f) => f.trace.trace_id}
        />
      </Card>
    </div>
  );
}

function PatternRow({ pattern, onInvestigate }: { pattern: PatternCard; onInvestigate: () => void }) {
  const anomalyOnly = pattern.discovered_by === "anomaly-only";
  return (
    <Card
      title={pattern.title}
      subtitle={pattern.signature}
      right={
        anomalyOnly ? (
          <Badge tone="accent" dot>anomaly only</Badge>
        ) : (
          <Badge tone="info">signal + anomaly</Badge>
        )
      }
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="font-mono text-[11px] text-muted">
            {pattern.size} traces · {pct(Number(pattern.impact.share_of_corpus ?? 0), 1)} of corpus ·{" "}
            {String(pattern.impact.escalated ?? 0)} escalated
          </div>
          <Button size="sm" onClick={onInvestigate}>
            Investigate →
          </Button>
        </div>
      }
    >
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">evidence</div>
          <ul className="space-y-1">
            {pattern.representative_evidence.map((e, i) => (
              <li key={i} className="text-xs leading-relaxed text-secondary">— {e}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">distinguishing features</div>
          <ul className="space-y-1">
            {pattern.top_features.map((f, i) => (
              <li key={i} className="font-mono text-[11px] text-secondary">{f}</li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

export default Discovery;
