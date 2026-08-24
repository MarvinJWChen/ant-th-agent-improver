import { Badge, ButtonPair, Card, CodeBlock, DiffView, ProvenanceBadge, SectionHeading } from "../components";
import { api } from "../lib/api";
import type { DiscoveryResult, ProposalResponse } from "../lib/api";
import { useAction, useAsync } from "../lib/state";
import { provenanceProps } from "./PatternDetail";
import { Failed, Loading } from "./Overview";

export function Proposals() {
  const disc = useAsync<DiscoveryResult>(() => api.discovery(), []);
  const health = useAsync(() => api.health(), []);
  const liveOK = Boolean((health.data as { live_available?: boolean } | null)?.live_available);

  if (disc.loading) return <Loading label="Loading patterns" />;
  if (disc.error || !disc.data) return <Failed message={disc.error ?? "no data"} />;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-6">
      <SectionHeading
        as="h1"
        title="Proposal-only remediations"
        subtitle="Not every failure is fixable by editing a prompt. These are written up for a human to action — this system does not apply them."
      />
      <Card title="Why these are not auto-applied">
        <p className="text-sm leading-relaxed text-secondary">
          The configuration patch in the previous step could be proven by replay because it changes only
          what the agent is told. A change to tool source code or to an operational process cannot be
          validated against a frozen world of recorded traces, so promoting it automatically would be
          claiming evidence that does not exist. They are proposals, clearly marked as such.
        </p>
      </Card>

      {disc.data.patterns.map((p) => (
        <ProposalCard key={p.pattern_id} patternId={p.pattern_id} title={p.title} liveOK={liveOK} />
      ))}
    </div>
  );
}

function ProposalCard({ patternId, title, liveOK }: { patternId: string; title: string; liveOK: boolean }) {
  const prop = useAction<ProposalResponse>();
  const r = prop.data;

  return (
    <Card
      title={title}
      subtitle={`${patternId} — generate the remediation proposal`}
      right={
        <div className="flex items-center gap-2">
          {r && <Badge tone="neutral" mono>{r.kind}</Badge>}
          {r && <ProvenanceBadge {...provenanceProps(r.provenance)} />}
        </div>
      }
    >
      <ButtonPair
        left={{
          label: "Show captured proposal",
          loading: prop.pending === "captured",
          onClick: () => void prop.run("captured", () => api.propose(patternId, "captured")),
        }}
        right={{
          label: "Generate live",
          loading: prop.pending === "live",
          disabled: !liveOK,
          disabledReason: "No ANTHROPIC_API_KEY is configured on this deployment.",
          onClick: () => void prop.run("live", () => api.propose(patternId, "live")),
        }}
      />
      {prop.error && <p className="mt-3 text-xs text-danger">{prop.error}</p>}

      {r?.code && (
        <div className="mt-4 space-y-3">
          <p className="text-sm leading-relaxed text-secondary">{r.code.rationale}</p>
          <DiffView diff={r.code.unified_diff} filename={r.code.file_path} />
          <div className="rounded border border-hairline bg-surface-0 p-3">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">suggested test</div>
            <p className="text-xs leading-relaxed text-secondary">{r.code.test_note}</p>
          </div>
        </div>
      )}

      {r?.process && (
        <div className="mt-4 space-y-3">
          <p className="text-sm leading-relaxed text-secondary">{r.process.problem_statement}</p>
          <ol className="space-y-2">
            {r.process.steps.map((s, i) => (
              <li key={i} className="rounded border border-hairline bg-surface-0 p-3">
                <div className="text-sm font-medium text-primary">
                  {i + 1}. {s.title}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-secondary">{s.detail}</p>
              </li>
            ))}
          </ol>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">owners</div>
              <div className="flex flex-wrap gap-1">
                {r.process.owners.map((o) => (
                  <Badge key={o} tone="neutral">{o}</Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">metrics to watch</div>
              <ul className="space-y-1">
                {r.process.metrics.map((m) => (
                  <li key={m} className="font-mono text-[11px] text-secondary">— {m}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {r?.config && (
        <div className="mt-4 space-y-3">
          <p className="text-sm leading-relaxed text-secondary">{r.config.rationale}</p>
          <CodeBlock
            filename="system_prompt (proposed)"
            code={r.config.system_prompt_after}
            maxHeightClassName="max-h-64"
          />
        </div>
      )}
    </Card>
  );
}

export default Proposals;
