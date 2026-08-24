import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Badge, Button, ButtonPair, Card, KeyValue, ProvenanceBadge, SectionHeading, Timeline,
} from "../components";
import type { TimelineItem } from "../components";
import { api, fmtMs } from "../lib/api";
import type {
  DiagnosisResponse, FlaggedTrace, PatchResponse, PatternCard, Provenance, TraceDetail,
} from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { Failed, Loading } from "./Overview";

export function provenanceProps(p: Provenance) {
  return {
    source: p.mode,
    verification: (p.mode === "live" ? "verified" : p.verified ? "verified" : "stale") as
      | "verified"
      | "stale",
    hashes: Object.entries(p.hashes).map(([label, value]) => ({ label, value })),
  };
}

export function traceToTimeline(t: TraceDetail): TimelineItem[] {
  return t.events.map((e) => ({
    id: `${t.trace_id}-${e.seq}`,
    seq: e.seq,
    type: e.type,
    title:
      e.type === "tool_call"
        ? `call ${e.tool_name}`
        : e.type === "tool_result"
          ? `result ${e.tool_name}`
          : e.type.replace("_", " "),
    payload:
      e.args || e.result
        ? JSON.stringify(e.args ?? e.result, null, 2)
        : e.content
          ? e.content
          : undefined,
    latencyMs: e.latency_ms || undefined,
    error: e.error ?? undefined,
    highlight: e.tool_name === "refund_execute" || e.type === "escalation",
  }));
}

export function PatternDetail() {
  const { patternId = "" } = useParams();
  const nav = useNavigate();
  const journey = useJourney();
  const [openTrace, setOpenTrace] = useState<string | null>(null);

  const pat = useAsync<{ pattern: PatternCard; flagged: FlaggedTrace[] }>(
    () => api.pattern(patternId),
    [patternId],
  );
  const diag = useAction<DiagnosisResponse>();
  const patch = useAction<PatchResponse>();
  const trace = useAsync<TraceDetail | null>(
    () => (openTrace ? api.trace(openTrace) : Promise.resolve(null)),
    [openTrace],
  );
  const health = useAsync(() => api.health(), []);
  const liveOK = Boolean((health.data as { live_available?: boolean } | null)?.live_available);

  if (pat.loading) return <Loading label="Loading pattern" />;
  if (pat.error || !pat.data) return <Failed message={pat.error ?? "no data"} />;

  const p = pat.data.pattern;
  const d = diag.data?.diagnosis;
  const kind = d?.remediation_kind;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-6">
      <SectionHeading
        as="h1"
        title={p.title}
        subtitle={p.signature}
        right={
          p.discovered_by === "anomaly-only" ? (
            <Badge tone="accent" dot>anomaly only</Badge>
          ) : (
            <Badge tone="info">signal + anomaly</Badge>
          )
        }
      />

      <Card title="Evidence from the corpus" subtitle={`${p.size} traces in this cluster.`}>
        <ul className="mb-4 space-y-1">
          {p.representative_evidence.map((e, i) => (
            <li key={i} className="text-sm leading-relaxed text-secondary">— {e}</li>
          ))}
        </ul>
        <div className="mb-2 text-[11px] uppercase tracking-wide text-muted">example traces</div>
        <div className="flex flex-wrap gap-2">
          {p.exemplar_trace_ids.map((id) => (
            <button
              key={id}
              onClick={() => setOpenTrace(openTrace === id ? null : id)}
              className={`rounded border px-2 py-1 font-mono text-xs transition-colors ${
                openTrace === id
                  ? "border-accent bg-accent-muted text-primary"
                  : "border-hairline text-secondary hover:border-hairline-strong"
              }`}
            >
              {id}
            </button>
          ))}
        </div>
        {openTrace && (
          <div className="mt-4 rounded border border-hairline bg-surface-0 p-3">
            {trace.loading && <span className="text-xs text-muted">Loading trace…</span>}
            {trace.data && (
              <>
                <div className="mb-2 font-mono text-[11px] text-muted">
                  {trace.data.trace_id} · {trace.data.intent} · {trace.data.turns} turns ·{" "}
                  {fmtMs(trace.data.duration_ms)} · {trace.data.outcome}
                </div>
                <Timeline items={traceToTimeline(trace.data)} />
              </>
            )}
          </div>
        )}
      </Card>

      <Card
        title="Diagnosis"
        subtitle="An LLM reads the cluster's traces and the agent's current configuration, and names the mechanism."
        right={diag.data && <ProvenanceBadge {...provenanceProps(diag.data.provenance)} />}
      >
        <ButtonPair
          left={{
            label: "Show captured diagnosis",
            loading: diag.pending === "captured",
            onClick: async () => {
              const r = await diag.run("captured", () => api.diagnose(patternId, "captured"));
              if (r) journey.add("diagnosed", patternId);
            },
          }}
          right={{
            label: "Run live diagnosis",
            loading: diag.pending === "live",
            disabled: !liveOK,
            disabledReason: "No ANTHROPIC_API_KEY is configured on this deployment.",
            onClick: async () => {
              const r = await diag.run("live", () => api.diagnose(patternId, "live"));
              if (r) journey.add("diagnosed", patternId);
            },
          }}
          caption="Both buttons run the same versioned task module. The left one returns a previously captured real run; the right one calls the model now."
        />
        {diag.error && <p className="mt-3 text-xs text-danger">{diag.error}</p>}
        {d && (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={d.verdict === "failure" ? "danger" : "ok"} dot>
                {d.verdict === "failure" ? "real failure" : "expected behaviour"}
              </Badge>
              <Badge tone="neutral" mono>{d.remediation_kind}</Badge>
              <Badge tone="neutral">{d.confidence} confidence</Badge>
            </div>
            {d.verdict === "expected_behaviour" && (
              <p className="rounded border border-ok/40 bg-ok/5 p-3 text-sm leading-relaxed text-secondary">
                The clustering step groups traces by behaviour — it cannot tell a problem from a rare but
                correct one. This cluster was judged correct, so nothing is proposed for it. A system that
                produced a remediation for every cluster would be manufacturing work.
              </p>
            )}
            <Field label={d.verdict === "failure" ? "Root cause" : "What this cluster is"} body={d.root_cause} />
            <Field label="Mechanism" body={d.mechanism} />
            <Field label="Why it recurs" body={d.why_it_recurs} />
            <KeyValue
              columns={2}
              items={[
                { key: "conf", label: "confidence", value: d.confidence },
                { key: "kind", label: "remediation", value: d.remediation_kind },
                { key: "cited", label: "cited traces", value: d.cited_trace_ids.join(", "), mono: true },
              ]}
            />
          </div>
        )}
      </Card>

      {d && d.verdict === "failure" && kind === "config" && (
        <Card
          title="Generate a configuration patch"
          subtitle="Prompt and tool-description edits only. Anything touching tool names or schemas is rejected before it can become a candidate."
          right={patch.data && <ProvenanceBadge {...provenanceProps(patch.data.provenance)} />}
        >
          <ButtonPair
            left={{
              label: "Show captured patch",
              loading: patch.pending === "captured",
              onClick: async () => {
                const r = await patch.run("captured", () => api.patch(patternId, "captured"));
                if (r) journey.add("patched", patternId);
              },
            }}
            right={{
              label: "Generate live patch",
              loading: patch.pending === "live",
              disabled: !liveOK,
              disabledReason: "No ANTHROPIC_API_KEY is configured on this deployment.",
              onClick: async () => {
                const r = await patch.run("live", () => api.patch(patternId, "live"));
                if (r) journey.add("patched", patternId);
              },
            }}
          />
          {patch.error && <p className="mt-3 text-xs text-danger">{patch.error}</p>}
          {patch.data && (
            <div className="mt-4 space-y-3">
              {patch.data.candidates.map((c) => (
                <div key={c.candidate_version} className="rounded border border-hairline bg-surface-0 p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-primary">{c.candidate_version}</span>
                    <Badge tone="neutral">{c.label}</Badge>
                    <Badge tone={c.within_edit_boundary ? "ok" : "danger"}>
                      {c.within_edit_boundary ? "within edit boundary" : "rejected"}
                    </Badge>
                  </div>
                  <p className="text-xs leading-relaxed text-secondary">{c.patch.rationale}</p>
                  {c.patch.risks.length > 0 && (
                    <p className="mt-2 text-xs leading-relaxed text-warn">
                      risk: {c.patch.risks.join(" ")}
                    </p>
                  )}
                  <div className="mt-2 font-mono text-[11px] text-muted">
                    {c.boundary_report.join(" · ")}
                  </div>
                </div>
              ))}
              <Button onClick={() => nav(`/replay/${patternId}`)}>
                Replay both candidates against the frozen world →
              </Button>
            </div>
          )}
        </Card>
      )}

      {d && d.verdict === "failure" && kind !== "config" && kind !== "none" && (
        <Card
          title="This one cannot be fixed by configuration"
          subtitle={d.remediation_summary}
        >
          <p className="mb-3 text-sm leading-relaxed text-secondary">
            The diagnosis classifies this as a <span className="font-mono">{kind}</span> remediation, so
            there is no prompt edit that would fix it. It is carried forward as a proposal for a human to
            action rather than something this system applies.
          </p>
          <Button variant="secondary" onClick={() => nav("/proposals")}>
            View the proposal →
          </Button>
        </Card>
      )}
    </div>
  );
}

function Field({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <p className="text-sm leading-relaxed text-secondary">{body}</p>
    </div>
  );
}

export default PatternDetail;
