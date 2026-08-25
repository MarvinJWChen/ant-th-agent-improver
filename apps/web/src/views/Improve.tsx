import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge, Button, Card, CodeBlock, ConfigDiff, DiffView, GateChecklist, KeyValue, ProvenanceBadge,
  SectionHeading, SplitPane, StatTile, Table, diffSummary,
} from "../components";
import { api, pct } from "../lib/api";
import type {
  AgentConfig, ArmRun, DiagnosisResponse, Health, LedgerRow, PatchResponse,
  PromoteResponse, ProposalResponse, ReplayRun, TracePair,
} from "../lib/api";
import { DEFAULT_AGENT_ID } from "../lib/journey";
import { useAction, useAsync, useJourney } from "../lib/state";
import { CapturedLive, Failed, KIND_LABEL, Loading, provenanceProps } from "../lib/ui";

/**
 * Step 5 — the one place a pattern gets improved.
 *
 * Which half runs is decided by the diagnosis, not by the navigation: a
 * config-remediable pattern gets patch → replay → gate → promote, and anything
 * else gets a written proposal. One route per pattern, so there is never a
 * page showing every pattern's remediation at once.
 */
export function Improve() {
  const { patternId = "" } = useParams();
  const diag = useAsync<DiagnosisResponse>(() => api.diagnose(patternId, "captured"), [patternId]);

  if (diag.loading) return <Loading label="Loading diagnosis" />;
  if (diag.error || !diag.data) return <Failed message={diag.error ?? "no diagnosis"} />;

  const d = diag.data.diagnosis;
  return d.remediation_kind === "config" ? (
    <ConfigImprove patternId={patternId} summary={d.remediation_summary} />
  ) : (
    <ProposalImprove patternId={patternId} kind={d.remediation_kind} summary={d.remediation_summary} />
  );
}

/** The two candidates exist to be compared, so the UI names what each one is. */
const CANDIDATE_META: Record<string, { title: string; gloss: string }> = {
  broad: {
    title: "Blanket fix",
    gloss: "the plausible over-correction",
  },
  surgical: {
    title: "Targeted fix",
    gloss: "only the clause the diagnosis names",
  },
};

/* ------------------------------------------------------------------ config path */

function ConfigImprove({ patternId, summary }: { patternId: string; summary: string }) {
  const journey = useJourney();
  const health = useAsync<Health>(() => api.health(), []);
  const liveOK = Boolean(health.data?.live_available);

  const patch = useAction<PatchResponse>();
  const run = useAction<ReplayRun>();
  const promote = useAction<PromoteResponse>();
  const configs = useAsync<AgentConfig[]>(() => api.configs(), [patch.data]);

  const [candidate, setCandidate] = useState<string | null>(null);
  const [openPair, setOpenPair] = useState<string | null>(null);

  const candidates = patch.data?.candidates ?? [];
  // The broad candidate first: the gate blocking it is the point of the step.
  const selected = candidate ?? candidates[0]?.candidate_version ?? "";
  const r = run.data;
  const active = configs.data?.find((c) => c.status === "active")?.version;

  const doPatch = (mode: "captured" | "live") => async () => {
    const res = await patch.run(mode, () => api.patch(patternId, mode));
    if (res) {
      journey.add("patched", patternId);
      setCandidate(null);
      run.setData(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <SectionHeading
        as="h1"
        title="Improve — configuration patch"
        subtitle="Prompt and tool-description wording only, proven against the frozen world before anything ships."
        right={active && <Badge tone="accent" mono dot>{active} active</Badge>}
      />

      <details className="rounded-lg border border-hairline bg-surface-1 px-4 py-3">
        <summary className="cursor-pointer select-none text-secondary hover:text-primary">
          What the diagnosis asked for
        </summary>
        <p className="mt-3 leading-relaxed text-secondary">{summary}</p>
      </details>

      <Card
        title="1 · Generate candidates"
        subtitle="Prompt and tool-description edits only. Anything touching tool names or schemas is rejected before it can become a candidate."
        right={patch.data && <ProvenanceBadge {...provenanceProps(patch.data.provenance)} />}
      >
        <CapturedLive
          capturedLabel="Show captured patch"
          liveLabel="Generate live patch"
          onCaptured={doPatch("captured")}
          onLive={doPatch("live")}
          pending={patch.pending}
          liveAvailable={liveOK}
          liveSeconds={60}
        />
        {patch.error && <p className="mt-4 text-danger">{patch.error}</p>}

        {candidates.length > 0 && (
          <div className="mt-6 space-y-4">
            <p className="leading-relaxed text-secondary">
              Two candidates, on purpose. The model was asked for the blunt fix a hurried
              engineer would ship <em>and</em> the minimal fix the diagnosis actually implies.{" "}
              <span className="text-primary">
                Both are within the edit boundary — neither is rejected by static validation.
              </span>{" "}
              Which one is safe to ship is decided by replay, not by reading them.
            </p>
            {candidates.map((c) => {
              const isSelected = selected === c.candidate_version;
              const meta = CANDIDATE_META[c.label] ?? { title: c.label, gloss: "" };
              const diffProps = {
                systemPromptBefore: c.patch.system_prompt_before,
                systemPromptAfter: c.patch.system_prompt_after,
                toolEdits: c.patch.tool_description_edits,
              };
              return (
                <div
                  key={c.candidate_version}
                  className={`rounded-lg border transition-colors ${
                    isSelected ? "border-accent bg-accent-muted" : "border-hairline"
                  }`}
                >
                  <button
                    onClick={() => {
                      setCandidate(c.candidate_version);
                      run.setData(null);
                    }}
                    className="block w-full p-4 text-left"
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="font-medium text-primary">{meta.title}</span>
                      <span className="font-mono text-muted">{c.candidate_version}</span>
                      <Badge tone={c.within_edit_boundary ? "ok" : "danger"}>
                        {c.within_edit_boundary ? "within edit boundary" : "rejected"}
                      </Badge>
                    </div>
                    <p className="mb-2 text-muted">
                      {meta.gloss} · {diffSummary(diffProps)}
                    </p>
                    <p className="leading-relaxed text-secondary">{c.patch.rationale}</p>
                    {c.patch.risks.length > 0 && (
                      <p className="mt-2 leading-relaxed text-warn">risk: {c.patch.risks[0]}</p>
                    )}
                  </button>
                  <div className="border-t border-hairline px-4 py-4">
                    <div className="mb-3 text-xs uppercase tracking-wide text-muted">
                      exactly what it changes
                    </div>
                    <ConfigDiff
                      {...diffProps}
                      fromLabel={c.parent_version}
                      toLabel={c.candidate_version}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {selected && (
        <Card
          title="2 · Evaluate against the frozen world"
          subtitle="The baseline is replayed from what production actually did. The candidate is re-executed, because a changed configuration may take a different path."
        >
          <CapturedLive
            capturedLabel={`Evaluate ${selected}`}
            liveLabel="Re-execute live"
            onCaptured={async () => {
              const res = await run.run("captured", () => api.replay(patternId, selected, "captured"));
              if (res) journey.add("replayed", patternId);
            }}
            onLive={async () => {
              const res = await run.run("live", () => api.replay(patternId, selected, "live"));
              if (res) journey.add("replayed", patternId);
            }}
            pending={run.pending}
            liveAvailable={liveOK}
            liveSeconds={240}
            caption="Cached mode replays a previously captured live counterfactual run — never the original trace's model outputs, which came from a different configuration."
          />
          {run.error && (
            run.error.startsWith("No captured counterfactual run") ? (
              // A refusal, not a failure: the candidate must be re-executed, and
              // no capture exists for it yet. Saying so plainly beats a red error.
              <div className="mt-4 rounded-lg border border-warn/40 bg-warn/5 p-4">
                <div className="mb-2 font-medium text-primary">
                  No captured run for this candidate
                </div>
                <p className="leading-relaxed text-secondary">{run.error}</p>
                <p className="mt-3 leading-relaxed text-muted">
                  Use <span className="text-secondary">Re-execute live</span> to run it now, or pick
                  a candidate that has captures.
                </p>
              </div>
            ) : (
              <p className="mt-4 text-danger">{run.error}</p>
            )
          )}
        </Card>
      )}

      {r && (
        <>
          <Card
            title="3 · Result"
            subtitle={`${r.cohort_target.length} target traces and ${r.cohort_control.length} controls, measured identically from each arm's Effect Ledger.`}
            right={<Badge tone="ok" dot>no production connector</Badge>}
          >
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatTile
                label="Trajectories diverged"
                value={`${r.pairs.filter((p) => p.trajectory_diverged).length}/${r.pairs.length}`}
                sublabel="candidate took a different path"
              />
              <StatTile
                label="External effects"
                value={String(r.world_isolation.external_effects_shadowed ?? 0)}
                sublabel="shadowed — none executed"
              />
              <StatTile
                label="World clones"
                value={String(r.world_isolation.clones_created ?? 0)}
                sublabel={`${r.world_isolation.source_worlds_mutated ?? 0} source worlds mutated`}
              />
              <StatTile
                label="Unsafe effects"
                value={String(r.candidate_metrics.unsafe_effects)}
                sublabel="fail-closed on unknown tools"
              />
            </div>

            <div className="mt-6 overflow-x-auto">
              <Table<MetricRow>
                columns={[
                  { key: "label", header: "Metric", render: (m) => m.label },
                  { key: "b", header: "Baseline", numeric: true, render: (m) => fmtMetric(m.k, m.b) },
                  { key: "c", header: "Candidate", numeric: true, render: (m) => fmtMetric(m.k, m.c) },
                  {
                    key: "delta",
                    header: "Change",
                    numeric: true,
                    render: (m) => {
                      const d = m.c - m.b;
                      if (Math.abs(d) < 1e-9) return <span className="text-muted">—</span>;
                      const better = m.good === "down" ? d < 0 : d > 0;
                      return (
                        <span className={better ? "text-ok" : "text-danger"}>
                          {d > 0 ? "+" : ""}
                          {fmtMetric(m.k, d)}
                        </span>
                      );
                    },
                  },
                ]}
                rows={metricRows(r)}
                rowKey={(m) => m.k}
              />
            </div>
          </Card>

          <Card
            title="4 · Promotion gate"
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
            <div className="mt-6 flex flex-col items-start gap-3">
              <Button
                size="lg"
                variant={r.gate.promotable ? "progress" : "secondary"}
                disabled={!r.gate.promotable}
                title={r.gate.promotable ? undefined : "The gate has not passed, so this candidate cannot be promoted."}
                loading={promote.pending === "go"}
                onClick={async () => {
                  const res = await promote.run("go", () => api.promote(r.run_id));
                  if (res?.promoted) journey.mark({ promotedVersion: res.active_version });
                }}
              >
                {r.promoted || promote.data?.promoted ? "Promoted ✓" : `Promote ${r.candidate_version}`}
              </Button>
              {promote.data && (
                <p className={promote.data.promoted ? "text-ok" : "text-danger"}>
                  {promote.data.message}
                </p>
              )}
              {promote.data?.promoted && (
                <a
                  href={`/agents/${DEFAULT_AGENT_ID}`}
                  className="text-accent underline-offset-4 hover:underline"
                >
                  See it on the agent’s configuration →
                </a>
              )}
              {!r.gate.promotable && (
                <p className="text-muted">
                  Promotion is disabled because the gate did not pass. Try the other candidate.
                </p>
              )}
            </div>
          </Card>

          <Card title="Per-trace outcomes" subtitle="Click a row to compare the two trajectories." noPadding>
            <Table<TracePair>
              maxHeightClassName="max-h-96"
              stickyHeader
              onRowClick={(p) => setOpenPair(openPair === p.trace_id ? null : p.trace_id)}
              columns={[
                { key: "trace_id", header: "Trace", render: (p) => <span className="font-mono">{p.trace_id}</span> },
                { key: "cohort", header: "Cohort", render: (p) => <Badge tone={p.cohort === "target" ? "accent" : "neutral"}>{p.cohort}</Badge> },
                { key: "b", header: "Baseline", render: (p) => <Badge tone={p.baseline_pass ? "ok" : "danger"}>{p.baseline_pass ? "pass" : "fail"}</Badge> },
                { key: "c", header: "Candidate", render: (p) => <Badge tone={p.candidate_pass ? "ok" : "danger"}>{p.candidate_pass ? "pass" : "fail"}</Badge> },
                { key: "div", header: "Trajectory", render: (p) => <span className="text-muted">{p.trajectory_diverged ? "diverged" : "same"}</span> },
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

/* ------------------------------------------------------------------ proposal path */

function ProposalImprove({
  patternId,
  kind,
  summary,
}: {
  patternId: string;
  kind: string;
  summary: string;
}) {
  const health = useAsync<Health>(() => api.health(), []);
  const liveOK = Boolean(health.data?.live_available);
  const prop = useAction<ProposalResponse>();
  const r = prop.data;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <SectionHeading
        as="h1"
        title={`Improve — ${KIND_LABEL[kind]?.toLowerCase() ?? kind}`}
        subtitle={summary}
        right={<Badge tone="neutral">proposal only</Badge>}
      />

      <Card title="Why this is not applied automatically">
        <p className="leading-relaxed text-secondary">
          A configuration patch can be proven by replay because it changes only what the agent is
          told. A change to tool source code or to an operational process cannot be validated
          against a frozen world of recorded traces, so promoting it automatically would be
          claiming evidence that does not exist.
        </p>
      </Card>

      <Card
        title="Proposal"
        right={r && <ProvenanceBadge {...provenanceProps(r.provenance)} />}
      >
        <CapturedLive
          capturedLabel="Show captured proposal"
          liveLabel="Generate live"
          onCaptured={() => void prop.run("captured", () => api.propose(patternId, "captured"))}
          onLive={() => void prop.run("live", () => api.propose(patternId, "live"))}
          pending={prop.pending}
          liveAvailable={liveOK}
          liveSeconds={90}
        />
        {prop.error && <p className="mt-4 text-danger">{prop.error}</p>}

        {r?.kind === "none" && (
          <div className="mt-6 rounded-lg border border-ok/40 bg-ok/5 p-4">
            <div className="mb-2 font-medium text-primary">No remediation proposed</div>
            <p className="leading-relaxed text-secondary">
              {r.explanation ?? "The diagnosis judged this cluster to be correct behaviour."}
            </p>
          </div>
        )}

        {r?.code && (
          <div className="mt-6 space-y-5">
            <p className="leading-relaxed text-secondary">{r.code.rationale}</p>
            <DiffView diff={r.code.unified_diff} filename={r.code.file_path} />
            <div className="rounded-lg border border-hairline bg-surface-0 p-4">
              <div className="mb-2 text-xs uppercase tracking-wide text-muted">suggested test</div>
              <p className="leading-relaxed text-secondary">{r.code.test_note}</p>
            </div>
          </div>
        )}

        {r?.process && (
          <div className="mt-6 space-y-5">
            <p className="leading-relaxed text-secondary">{r.process.problem_statement}</p>
            <ol className="space-y-3">
              {r.process.steps.map((s, i) => (
                <li key={i} className="rounded-lg border border-hairline bg-surface-0 p-4">
                  <div className="font-medium text-primary">
                    {i + 1}. {s.title}
                  </div>
                  <p className="mt-2 leading-relaxed text-secondary">{s.detail}</p>
                </li>
              ))}
            </ol>
            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <div className="mb-2 text-xs uppercase tracking-wide text-muted">owners</div>
                <div className="flex flex-wrap gap-2">
                  {r.process.owners.map((o) => (
                    <Badge key={o} tone="neutral">{o}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 text-xs uppercase tracking-wide text-muted">metrics to watch</div>
                <ul className="space-y-1">
                  {r.process.metrics.map((m) => (
                    <li key={m} className="font-mono text-secondary">— {m}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {r?.config && (
          <div className="mt-6 space-y-4">
            <p className="leading-relaxed text-secondary">{r.config.rationale}</p>
            <CodeBlock
              filename="system_prompt (proposed)"
              code={r.config.system_prompt_after}
              maxHeightClassName="max-h-72"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ shared bits */

interface MetricRow {
  k: string;
  label: string;
  b: number;
  c: number;
  good: "down" | "up";
}

function fmtMetric(k: string, v: number): string {
  return k === "avg_turns" ? v.toFixed(2) : pct(v, 1);
}

function metricRows(r: ReplayRun): MetricRow[] {
  return [
    { k: "premature_escalation_rate", label: "Avoidable escalations", b: r.baseline_metrics.premature_escalation_rate, c: r.candidate_metrics.premature_escalation_rate, good: "down" },
    { k: "double_refund_rate", label: "Double refunds", b: r.baseline_metrics.double_refund_rate, c: r.candidate_metrics.double_refund_rate, good: "down" },
    { k: "duplicate_confirmation_rate", label: "Duplicate confirmations", b: r.baseline_metrics.duplicate_confirmation_rate, c: r.candidate_metrics.duplicate_confirmation_rate, good: "down" },
    { k: "resolution_rate", label: "Self-resolved", b: r.baseline_metrics.resolution_rate, c: r.candidate_metrics.resolution_rate, good: "up" },
    { k: "avg_turns", label: "Average turns", b: r.baseline_metrics.avg_turns, c: r.candidate_metrics.avg_turns, good: "down" },
  ];
}

function firstDivergence(a: ArmRun, b: ArmRun): number {
  const ta = a.steps.filter((s) => s.kind === "tool_call").map((s) => s.tool_name);
  const tb = b.steps.filter((s) => s.kind === "tool_call").map((s) => s.tool_name);
  for (let i = 0; i < Math.max(ta.length, tb.length); i++) if (ta[i] !== tb[i]) return i;
  return -1;
}

const DISPOSITION_TONE: Record<string, "ok" | "warn" | "danger" | "info"> = {
  READ_FROM_CLONE: "info",
  APPLIED_TO_CLONE: "ok",
  SHADOWED: "warn",
  BLOCKED_UNKNOWN_EFFECT: "danger",
};

function PairDetail({ pair }: { pair: TracePair }) {
  const at = firstDivergence(pair.baseline, pair.candidate);
  return (
    <Card
      title={`Trajectories — ${pair.trace_id}`}
      subtitle={
        pair.trajectory_diverged
          ? "The candidate is not a replay. From the highlighted call onward it did something different."
          : "Both arms took the same path."
      }
      right={
        <Badge tone={pair.regression ? "danger" : pair.candidate_pass ? "ok" : "warn"} dot>
          {pair.regression ? "regression" : pair.candidate_pass ? "candidate passes" : "candidate fails"}
        </Badge>
      }
    >
      <SplitPane
        leftLabel="Baseline"
        leftMeta={<Badge tone="neutral" mono>replayed</Badge>}
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
    <div className="space-y-4">
      <KeyValue
        items={[
          { key: "start", label: "clone at start", value: arm.clone_sha256, mono: true, truncateMiddle: true },
          { key: "after", label: "clone after run", value: arm.clone_sha256_after, mono: true, truncateMiddle: true },
          { key: "src", label: "source world", value: arm.source_world_sha256, mono: true, truncateMiddle: true },
        ]}
      />
      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-muted">tool calls</div>
        <ol className="space-y-1">
          {arm.steps
            .filter((s) => s.kind === "tool_call")
            .map((s, i) => {
              const diverged = divergeAt >= 0 && i >= divergeAt;
              return (
                <li
                  key={s.seq}
                  className={`border-l-2 pl-3 font-mono ${
                    diverged ? "border-accent text-primary" : "border-transparent text-secondary"
                  }`}
                >
                  {s.tool_name}
                </li>
              );
            })}
          {arm.steps.filter((s) => s.kind === "tool_call").length === 0 && (
            <li className="text-muted">no tool calls</li>
          )}
        </ol>
      </div>
      <div>
        <div className="mb-2 text-xs uppercase tracking-wide text-muted">effect ledger</div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <tbody>
              {arm.ledger.map((l: LedgerRow) => (
                <tr key={l.seq} className="border-b border-hairline/50">
                  <td className="py-2 pr-3 font-mono text-secondary">{l.tool}</td>
                  <td className="py-2">
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

export default Improve;
