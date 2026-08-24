import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge, Button, ButtonPair, Card, GateChecklist, KeyValue, ProvenanceBadge,
  SectionHeading, SplitPane, StatTile, Table,
} from "../components";
import { api, pct } from "../lib/api";
import type { AgentConfig, ArmRun, LedgerRow, PromoteResponse, ReplayRun, TracePair } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { provenanceProps } from "./PatternDetail";
import { Failed, Loading } from "./Overview";

const DISPOSITION_TONE: Record<string, "ok" | "warn" | "danger" | "info"> = {
  READ_FROM_CLONE: "info",
  APPLIED_TO_CLONE: "ok",
  SHADOWED: "warn",
  BLOCKED_UNKNOWN_EFFECT: "danger",
};

export function Replay() {
  const { patternId = "" } = useParams();
  const journey = useJourney();
  const configs = useAsync<AgentConfig[]>(() => api.configs(), []);
  const health = useAsync(() => api.health(), []);
  const run = useAction<ReplayRun>();
  const promote = useAction<PromoteResponse>();
  const [candidate, setCandidate] = useState<string | null>(null);
  const [openPair, setOpenPair] = useState<string | null>(null);

  const liveOK = Boolean((health.data as { live_available?: boolean } | null)?.live_available);
  const r = run.data;

  if (configs.loading) return <Loading label="Loading configurations" />;
  if (configs.error) return <Failed message={configs.error} />;

  const prefix = `v2-${patternId.toLowerCase()}-`;
  const candidates = (configs.data ?? []).filter((c) => c.version.startsWith(prefix));
  // Default to the second candidate: the generator is asked for a broad option
  // first and a surgical one second, and the surgical one is the interesting run.
  const selected = candidate ?? candidates[candidates.length - 1]?.version ?? "";

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-6">
      <SectionHeading
        as="h1"
        title="Counterfactual replay"
        subtitle="The baseline is replayed from what production actually did. The candidate is re-executed, because a changed configuration may take a different path."
      />

      <Card title="Choose a candidate" subtitle="Both were generated from the same diagnosis.">
        {candidates.length === 0 && (
          <p className="text-sm text-muted">
            No candidate configurations exist for this pattern yet. Generate a config patch on the
            pattern page first.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {candidates.map((c) => (
            <button
              key={c.version}
              onClick={() => setCandidate(c.version)}
              className={`rounded border px-3 py-2 text-left transition-colors ${
                selected === c.version
                  ? "border-accent bg-accent-muted"
                  : "border-hairline hover:border-hairline-strong"
              }`}
            >
              <div className="font-mono text-xs text-primary">{c.version}</div>
              <div className="text-[11px] text-muted">{c.notes ?? ""}</div>
            </button>
          ))}
        </div>

        <div className="mt-4">
          <ButtonPair
            left={{
              label: "Use captured counterfactual runs",
              loading: run.pending === "captured",
              onClick: async () => {
                const res = await run.run("captured", () => api.replay(patternId, selected, "captured"));
                if (res) journey.add("replayed", patternId);
              },
            }}
            right={{
              label: "Re-execute live",
              loading: run.pending === "live",
              disabled: !liveOK,
              disabledReason: "No ANTHROPIC_API_KEY is configured on this deployment.",
              onClick: async () => {
                const res = await run.run("live", () => api.replay(patternId, selected, "live"));
                if (res) journey.add("replayed", patternId);
              },
            }}
            caption="Cached mode returns a previously captured live counterfactual run — never the original trace's model outputs, which came from a different configuration."
          />
          {run.error && <p className="mt-3 text-xs text-danger">{run.error}</p>}
        </div>
      </Card>

      {r && (
        <>
          <Card
            title="World isolation"
            subtitle="Every arm ran against its own copy. The recorded worlds were verified unchanged afterwards."
            right={<Badge tone="ok" dot>no production connector</Badge>}
          >
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatTile label="Worlds frozen" value={String(r.world_isolation.worlds_frozen ?? 0)} />
              <StatTile label="Clones created" value={String(r.world_isolation.clones_created ?? 0)} sublabel={`${r.world_isolation.distinct_clone_hashes ?? 0} distinct hashes`} />
              <StatTile label="External effects shadowed" value={String(r.world_isolation.external_effects_shadowed ?? 0)} sublabel="none executed" />
              <StatTile label="Source worlds mutated" value={String(r.world_isolation.source_worlds_mutated ?? 0)} sublabel="verified by hash" />
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted">{r.world_isolation.note}</p>
          </Card>

          <Card title="Metrics" subtitle={`${r.cohort_target.length} target traces and ${r.cohort_control.length} controls, measured identically from each arm's Effect Ledger.`} noPadding>
            <Table<{ k: string; label: string; b: number; c: number; good: "down" | "up" }>
              columns={[
                { key: "label", header: "Metric", render: (m) => <span className="text-xs">{m.label}</span> },
                { key: "b", header: "Baseline", numeric: true, render: (m) => <span className="font-mono text-xs">{fmtMetric(m.k, m.b)}</span> },
                { key: "c", header: "Candidate", numeric: true, render: (m) => <span className="font-mono text-xs">{fmtMetric(m.k, m.c)}</span> },
                {
                  key: "delta",
                  header: "Change",
                  numeric: true,
                  render: (m) => {
                    const d = m.c - m.b;
                    if (Math.abs(d) < 1e-9) return <span className="text-xs text-muted">—</span>;
                    const better = m.good === "down" ? d < 0 : d > 0;
                    return (
                      <span className={`font-mono text-xs ${better ? "text-ok" : "text-danger"}`}>
                        {d > 0 ? "+" : ""}{fmtMetric(m.k, d)}
                      </span>
                    );
                  },
                },
              ]}
              rows={metricRows(r)}
              rowKey={(m) => m.k}
            />
          </Card>

          <Card
            title="Promotion gate"
            subtitle="All four checks must pass. There is no override."
            right={<ProvenanceBadge {...provenanceProps(r.provenance)} />}
          >
            <GateChecklist
              verdict={r.gate.verdict}
              checks={r.gate.checks.map((c) => ({
                id: c.id,
                label: c.label,
                status: c.status,
                detail: c.detail,
              }))}
            />
            <div className="mt-4 flex flex-col items-start gap-2">
              <Button
                variant={r.gate.promotable ? "primary" : "secondary"}
                disabled={!r.gate.promotable}
                title={r.gate.promotable ? undefined : "The gate has not passed, so this candidate cannot be promoted."}
                loading={promote.pending === "go"}
                onClick={async () => {
                  const res = await promote.run("go", () => api.promote(r.run_id));
                  if (res?.promoted) journey.mark({ promotedVersion: res.active_version });
                }}
              >
                {r.promoted || promote.data?.promoted ? "Promoted" : `Promote ${r.candidate_version}`}
              </Button>
              {promote.data && (
                <p className={`text-xs ${promote.data.promoted ? "text-ok" : "text-danger"}`}>
                  {promote.data.message}
                </p>
              )}
              {!r.gate.promotable && (
                <p className="text-xs text-muted">
                  Promotion is disabled because the gate did not pass. Try the other candidate.
                </p>
              )}
            </div>
          </Card>

          <Card title="Per-trace outcomes" subtitle="Click a row to compare the two trajectories." noPadding>
            <Table<TracePair>
              maxHeightClassName="max-h-80"
              stickyHeader
              onRowClick={(p) => setOpenPair(openPair === p.trace_id ? null : p.trace_id)}
              columns={[
                { key: "trace_id", header: "Trace", render: (p) => <span className="font-mono text-xs">{p.trace_id}</span> },
                { key: "cohort", header: "Cohort", render: (p) => <Badge tone={p.cohort === "target" ? "accent" : "neutral"}>{p.cohort}</Badge> },
                { key: "b", header: "Baseline", render: (p) => <Badge tone={p.baseline_pass ? "ok" : "danger"}>{p.baseline_pass ? "pass" : "fail"}</Badge> },
                { key: "c", header: "Candidate", render: (p) => <Badge tone={p.candidate_pass ? "ok" : "danger"}>{p.candidate_pass ? "pass" : "fail"}</Badge> },
                { key: "div", header: "Trajectory", render: (p) => <span className="text-xs text-muted">{p.trajectory_diverged ? "diverged" : "same"}</span> },
                { key: "reg", header: "", render: (p) => (p.regression ? <Badge tone="danger" dot>regression</Badge> : null) },
              ]}
              rows={r.pairs}
              rowKey={(p) => p.trace_id}
            />
          </Card>

          {openPair && <PairDetail pair={r.pairs.find((p) => p.trace_id === openPair)!} />}
        </>
      )}
    </div>
  );
}

function fmtMetric(k: string, v: number): string {
  return k === "avg_turns" || k === "unsafe_effects" || k === "external_calls_executed"
    ? v.toFixed(2)
    : pct(v, 1);
}

function metricRows(r: ReplayRun) {
  const rows: { k: string; label: string; b: number; c: number; good: "down" | "up" }[] = [
    { k: "double_refund_rate", label: "Double refunds", b: r.baseline_metrics.double_refund_rate, c: r.candidate_metrics.double_refund_rate, good: "down" },
    { k: "duplicate_confirmation_rate", label: "Duplicate confirmations", b: r.baseline_metrics.duplicate_confirmation_rate, c: r.candidate_metrics.duplicate_confirmation_rate, good: "down" },
    { k: "premature_escalation_rate", label: "Avoidable escalations", b: r.baseline_metrics.premature_escalation_rate, c: r.candidate_metrics.premature_escalation_rate, good: "down" },
    { k: "resolution_rate", label: "Self-resolved", b: r.baseline_metrics.resolution_rate, c: r.candidate_metrics.resolution_rate, good: "up" },
    { k: "avg_turns", label: "Average turns", b: r.baseline_metrics.avg_turns, c: r.candidate_metrics.avg_turns, good: "down" },
    { k: "unsafe_effects", label: "Unsafe effects", b: r.baseline_metrics.unsafe_effects, c: r.candidate_metrics.unsafe_effects, good: "down" },
    { k: "external_calls_executed", label: "External calls executed", b: r.baseline_metrics.external_calls_executed, c: r.candidate_metrics.external_calls_executed, good: "down" },
  ];
  return rows;
}

function firstDivergence(a: ArmRun, b: ArmRun): number {
  const ta = a.steps.filter((s) => s.kind === "tool_call").map((s) => s.tool_name);
  const tb = b.steps.filter((s) => s.kind === "tool_call").map((s) => s.tool_name);
  const n = Math.max(ta.length, tb.length);
  for (let i = 0; i < n; i++) if (ta[i] !== tb[i]) return i;
  return -1;
}

function PairDetail({ pair }: { pair: TracePair }) {
  const at = firstDivergence(pair.baseline, pair.candidate);
  return (
    <Card
      title={`Trajectories — ${pair.trace_id}`}
      subtitle={
        pair.trajectory_diverged
          ? "The candidate is not a replay — it was re-executed, and from the highlighted call onward it did something different."
          : "Both arms took the same path. The candidate changed nothing here."
      }
      right={
        <Badge tone={pair.regression ? "danger" : pair.candidate_pass ? "ok" : "warn"} dot>
          {pair.regression ? "regression" : pair.candidate_pass ? "candidate passes" : "candidate fails"}
        </Badge>
      }
    >
      <SplitPane
        leftLabel="Baseline"
        leftMeta={<Badge tone="neutral" mono>replayed from the recording</Badge>}
        rightLabel="Candidate"
        rightMeta={<Badge tone="accent" mono>re-executed</Badge>}
        left={<ArmPanel arm={pair.baseline} divergeAt={at} />}
        right={<ArmPanel arm={pair.candidate} divergeAt={at} />}
      />
    </Card>
  );
}

function ArmPanel({ arm, divergeAt = -1 }: { arm: ArmRun; divergeAt?: number }) {
  return (
    <div className="space-y-3">
      <KeyValue
        items={[
          { key: "src", label: "source world", value: arm.source_world_sha256, mono: true, truncateMiddle: true },
          { key: "clone", label: "clone at start", value: arm.clone_sha256, mono: true, truncateMiddle: true },
          { key: "after", label: "clone after run", value: arm.clone_sha256_after, mono: true, truncateMiddle: true },
          { key: "outcome", label: "outcome", value: arm.outcome },
        ]}
      />
      <div>
        <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">tool calls</div>
        <ol className="space-y-1">
          {arm.steps.filter((s) => s.kind === "tool_call").map((s, i) => {
            const diverged = divergeAt >= 0 && i >= divergeAt;
            return (
              <li
                key={s.seq}
                className={`border-l-2 pl-2 font-mono text-[11px] ${
                  diverged ? "border-accent text-primary" : "border-transparent text-secondary"
                }`}
              >
                {s.tool_name}({Object.values(s.args ?? {}).join(", ")})
              </li>
            );
          })}
          {arm.steps.filter((s) => s.kind === "tool_call").length === 0 && (
            <li className="text-[11px] text-muted">no tool calls</li>
          )}
        </ol>
      </div>
      <div>
        <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">effect ledger</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <tbody>
              {arm.ledger.map((l: LedgerRow) => (
                <tr key={l.seq} className="border-b border-hairline/50">
                  <td className="py-1 pr-2 font-mono text-secondary">{l.tool}</td>
                  <td className="py-1 pr-2 font-mono text-muted">{l.target}</td>
                  <td className="py-1">
                    <Badge tone={DISPOSITION_TONE[l.disposition] ?? "neutral"} mono>
                      {l.disposition.replace(/_/g, " ").toLowerCase()}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Replay;
