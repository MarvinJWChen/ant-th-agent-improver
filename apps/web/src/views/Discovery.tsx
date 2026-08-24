import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, SectionHeading, StatTile, Table } from "../components";
import { api, fmtMs, pct } from "../lib/api";
import type { DiscoveryResult, FlaggedTrace, PatternCard } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { Failed, Loading } from "../lib/ui";

export function Discovery() {
  const nav = useNavigate();
  const journey = useJourney();
  const { data, error, loading, reload } = useAsync<DiscoveryResult>(() => api.discovery(), []);
  const rerun = useAction<DiscoveryResult>();
  const [showQueue, setShowQueue] = useState(false);

  if (loading) return <Loading label="Clustering flagged traces" />;
  if (error || !data) return <Failed message={error ?? "no data"} />;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <SectionHeading
        as="h1"
        title="Recurring behaviours"
        subtitle={`${data.patterns.length} clusters found in ${data.n_traces_scanned.toLocaleString()} production traces. Some are failures; some are simply uncommon and correct.`}
        right={
          <Button
            variant="secondary"
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

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Traces scanned" value={data.n_traces_scanned.toLocaleString()} sublabel="every trace, this request" />
        <StatTile label="Sent to clustering" value={data.n_flagged} sublabel={`${pct(data.n_flagged / data.n_traces_scanned, 0)} matched a signal`} />
        <StatTile label="Behaviours found" value={data.patterns.length} sublabel={`k chosen by silhouette (${data.silhouette.toFixed(2)})`} />
        <StatTile label="Found by anomaly only" value={data.n_anomaly_only} sublabel="no observable signal fired" />
      </div>

      <Card title="How these were found">
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <div className="mb-2 font-medium text-primary">Observable failure signals</div>
            <p className="leading-relaxed text-secondary">
              Four generic signals — the agent didn't finish, an effect repeated at one target, an
              effect issued at a target already read as finished, a retry after an ambiguous
              timeout. None of them names a refund, an email, or an SLA.
            </p>
          </div>
          <div>
            <div className="mb-2 font-medium text-primary">Generic anomaly model</div>
            <p className="leading-relaxed text-secondary">
              Scores every trace on incompletion, cost relative to same-intent peers, and shape
              isolation. It contributed {data.n_anomaly_only} traces no signal caught.
            </p>
          </div>
        </div>
        <p className="mt-6 border-t border-hairline pt-5 leading-relaxed text-muted">
          The {data.n_flagged} traces above are a <span className="text-secondary">review queue</span>, not
          a failure count — both signals are deliberately high-recall. Separating genuine failures
          from rare-but-correct behaviour is what the clustering and the diagnosis do next.
        </p>
      </Card>

      <div className="space-y-4">
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

      <div>
        <button
          onClick={() => setShowQueue((v) => !v)}
          className="text-muted underline-offset-4 hover:text-secondary hover:underline"
        >
          {showQueue ? "Hide" : "Show"} the raw review queue ({data.n_flagged} traces)
        </button>
        {showQueue && (
          <Card className="mt-4" noPadding>
            <Table<FlaggedTrace>
              maxHeightClassName="max-h-96"
              stickyHeader
              columns={[
                { key: "trace_id", header: "Trace", render: (f) => <span className="font-mono">{f.trace.trace_id}</span> },
                { key: "intent", header: "Intent", render: (f) => f.trace.intent },
                { key: "outcome", header: "Outcome", render: (f) => f.trace.outcome },
                { key: "duration", header: "Duration", numeric: true, render: (f) => fmtMs(f.trace.duration_ms) },
                { key: "score", header: "Anomaly", numeric: true, render: (f) => f.anomaly_score.toFixed(3) },
                {
                  key: "how",
                  header: "Found by",
                  render: (f) =>
                    f.rule_flagged ? <Badge tone="info">signal</Badge> : <Badge tone="accent" dot>anomaly only</Badge>,
                },
              ]}
              rows={data.flagged.slice(0, 120)}
              rowKey={(f) => f.trace.trace_id}
            />
          </Card>
        )}
      </div>
    </div>
  );
}

function PatternRow({ pattern, onInvestigate }: { pattern: PatternCard; onInvestigate: () => void }) {
  return (
    <Card
      title={pattern.title}
      subtitle={pattern.signature}
      right={
        <Badge tone={pattern.discovered_by === "anomaly-only" ? "accent" : "info"} dot>
          {pattern.discovered_by === "anomaly-only" ? "anomaly only" : "signal + anomaly"}
        </Badge>
      }
      footer={
        <div className="flex flex-wrap items-center justify-between gap-4">
          <span className="font-mono text-muted">
            {pattern.size} traces · {pct(Number(pattern.impact.share_of_corpus ?? 0), 1)} of corpus
          </span>
          <Button size="lg" onClick={onInvestigate}>
            Investigate →
          </Button>
        </div>
      }
    >
      <ul className="space-y-2">
        {pattern.representative_evidence.slice(0, 2).map((e, i) => (
          <li key={i} className="leading-relaxed text-secondary">
            — {e}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default Discovery;
