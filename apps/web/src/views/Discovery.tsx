import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, SectionHeading, StatTile, Table } from "../components";
import { api, fmtMs, pct } from "../lib/api";
import type { DiscoveryResult, FlaggedTrace, PatternCard, RemediationKind } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { Failed, Loading } from "../lib/ui";

/**
 * Clusters are grouped by the remediation their diagnosis called for, so the
 * distinct *kinds* of fix are visible before clicking into anything. The
 * grouping is a read of captured diagnoses, never a new inference, and nothing
 * is hidden — the smaller clusters collapse to one line rather than disappear.
 */
const GROUPS: { kind: RemediationKind; title: string; blurb: string }[] = [
  {
    kind: "config",
    title: "Fixable in agent configuration",
    blurb: "Prompt or tool-description wording. Provable by replay, so these can be promoted.",
  },
  {
    kind: "code",
    title: "Needs a tool code change",
    blurb: "The tool contract itself is unsafe. No instruction to the agent can fix it.",
  },
  {
    kind: "process",
    title: "Needs an operational change",
    blurb: "The agent behaved reasonably. The fix is a policy, a metric, or an upstream system.",
  },
  {
    kind: "none",
    title: "Not a problem",
    blurb: "Uncommon but correct behaviour. Nothing is proposed for these.",
  },
];

/** Cards shown in full per group; the remainder collapse to one line each. */
const EXPANDED_PER_GROUP = 2;

export function Discovery() {
  const nav = useNavigate();
  const journey = useJourney();
  const { data, error, loading, reload } = useAsync<DiscoveryResult>(() => api.discovery(), []);
  const rerun = useAction<DiscoveryResult>();
  const [showQueue, setShowQueue] = useState(false);

  if (loading) return <Loading label="Clustering flagged traces" />;
  if (error || !data) return <Failed message={error ?? "no data"} />;

  const open = (p: PatternCard) => {
    journey.mark({ activePatternId: p.pattern_id });
    nav(`/patterns/${p.pattern_id}`);
  };

  const undiagnosed = data.patterns.filter((p) => !p.remediation_kind);
  const failures = data.patterns.filter((p) => p.verdict === "failure").length;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <SectionHeading
        as="h1"
        title="Recurring behaviours"
        subtitle={`${data.patterns.length} clusters in ${data.n_traces_scanned.toLocaleString()} production traces — ${failures} are real failures, the rest are uncommon but correct.`}
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

      {GROUPS.map((g) => {
        const members = data.patterns
          .filter((p) => p.remediation_kind === g.kind)
          .sort((a, b) => b.size - a.size);
        if (members.length === 0) return null;
        return (
          <PatternGroup key={g.kind} group={g} members={members} onOpen={open} />
        );
      })}

      {undiagnosed.length > 0 && (
        <PatternGroup
          group={{
            kind: "none",
            title: "Not yet diagnosed",
            blurb: "No diagnosis has been captured for these yet — open one to run it.",
          }}
          members={undiagnosed}
          onOpen={open}
        />
      )}

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
          The {data.n_flagged} traces are a <span className="text-secondary">review queue</span>, not a
          failure count — both signals are deliberately high-recall. Grouping above comes from each
          cluster's own diagnosis; the clusterer has no view on what kind of fix anything needs.
        </p>
      </Card>

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

function PatternGroup({
  group,
  members,
  onOpen,
}: {
  group: { kind: RemediationKind; title: string; blurb: string };
  members: PatternCard[];
  onOpen: (p: PatternCard) => void;
}) {
  const isNone = group.kind === "none";
  const [expanded, setExpanded] = useState(!isNone);
  const shown = expanded ? members.slice(0, EXPANDED_PER_GROUP) : [];
  const rest = expanded ? members.slice(EXPANDED_PER_GROUP) : members;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-hairline pb-3">
        <div>
          <h2 className="text-xl font-semibold text-primary">
            {group.title}{" "}
            <span className="font-mono text-muted">· {members.length}</span>
          </h2>
          <p className="mt-1 text-muted">{group.blurb}</p>
        </div>
        {isNone && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-muted underline-offset-4 hover:text-secondary hover:underline"
          >
            {expanded ? "collapse" : "expand"}
          </button>
        )}
      </div>

      {shown.map((p) => (
        <PatternRow key={p.pattern_id} pattern={p} onInvestigate={() => onOpen(p)} />
      ))}

      {rest.length > 0 && (
        <div className="divide-y divide-hairline rounded-lg border border-hairline">
          {rest.map((p) => (
            <button
              key={p.pattern_id}
              onClick={() => onOpen(p)}
              className="flex w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-2"
            >
              <span className="min-w-0 flex-1 truncate text-secondary">{p.title}</span>
              <span className="font-mono text-muted">{p.size} traces</span>
              <span className="text-ok">Investigate →</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function PatternRow({ pattern, onInvestigate }: { pattern: PatternCard; onInvestigate: () => void }) {
  return (
    <Card
      title={pattern.title}
      subtitle={pattern.signature}
      right={
        <div className="flex items-center gap-2">
          {pattern.verdict && (
            <Badge tone={pattern.verdict === "failure" ? "danger" : "ok"} dot>
              {pattern.verdict === "failure" ? "failure" : "expected"}
            </Badge>
          )}
          <Badge tone={pattern.discovered_by === "anomaly-only" ? "accent" : "info"}>
            {pattern.discovered_by === "anomaly-only" ? "anomaly only" : "signal + anomaly"}
          </Badge>
        </div>
      }
      footer={
        <div className="flex flex-wrap items-center justify-between gap-4">
          <span className="font-mono text-muted">
            {pattern.size} traces · {pct(Number(pattern.impact.share_of_corpus ?? 0), 1)} of corpus
          </span>
          <Button size="lg" variant="progress" onClick={onInvestigate}>
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
