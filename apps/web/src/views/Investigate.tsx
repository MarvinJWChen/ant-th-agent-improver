import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, KeyValue, ProvenanceBadge, SectionHeading, Timeline } from "../components";
import { api, fmtMs } from "../lib/api";
import type { DiagnosisResponse, FlaggedTrace, Health, PatternCard, TraceDetail } from "../lib/api";
import { useAction, useAsync, useJourney } from "../lib/state";
import { CapturedLive, Failed, KIND_LABEL, Loading, provenanceProps, traceToTimeline } from "../lib/ui";

/**
 * Step 4 — evidence, then a diagnosis, then exactly one way forward.
 *
 * Everything about *fixing* the pattern lives in the next step. Keeping the
 * remediation work off this page is what makes the forward action obvious.
 */
export function Investigate() {
  const { patternId = "" } = useParams();
  const nav = useNavigate();
  const journey = useJourney();
  const [openTrace, setOpenTrace] = useState<string | null>(null);

  const pat = useAsync<{ pattern: PatternCard; flagged: FlaggedTrace[] }>(
    () => api.pattern(patternId),
    [patternId],
  );
  const diag = useAction<DiagnosisResponse>();
  const trace = useAsync<TraceDetail | null>(
    () => (openTrace ? api.trace(openTrace) : Promise.resolve(null)),
    [openTrace],
  );
  const health = useAsync<Health>(() => api.health(), []);
  const liveOK = Boolean(health.data?.live_available);

  if (pat.loading) return <Loading label="Loading pattern" />;
  if (pat.error || !pat.data) return <Failed message={pat.error ?? "no data"} />;

  const p = pat.data.pattern;
  const d = diag.data?.diagnosis;
  const sum = diag.data?.summary ?? null;

  const runDiagnosis = (mode: "captured" | "live") => async () => {
    const r = await diag.run(mode, () => api.diagnose(patternId, mode));
    if (r) journey.add("diagnosed", patternId);
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <SectionHeading
        as="h1"
        title={p.title}
        subtitle={p.signature}
        right={
          <Badge tone={p.discovered_by === "anomaly-only" ? "accent" : "info"} dot>
            {p.discovered_by === "anomaly-only" ? "anomaly only" : "signal + anomaly"}
          </Badge>
        }
      />

      <Card title="Evidence" subtitle={`${p.size} traces behave this way.`}>
        <ul className="mb-6 space-y-2">
          {p.representative_evidence.map((e, i) => (
            <li key={i} className="leading-relaxed text-secondary">
              — {e}
            </li>
          ))}
        </ul>
        <div className="mb-3 text-muted">Open a trace to see what actually happened:</div>
        <div className="flex flex-wrap gap-2">
          {p.exemplar_trace_ids.map((id) => (
            <button
              key={id}
              onClick={() => setOpenTrace(openTrace === id ? null : id)}
              className={`rounded-md border px-3 py-2 font-mono transition-colors ${
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
          <div className="mt-5 rounded-lg border border-hairline bg-surface-0 p-4">
            {trace.loading && <span className="text-muted">Loading trace…</span>}
            {trace.data && (
              <>
                <div className="mb-3 font-mono text-muted">
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
        subtitle="A model reads this cluster's traces alongside the agent's current configuration, and names the mechanism."
        right={diag.data && <ProvenanceBadge {...provenanceProps(diag.data.provenance)} />}
      >
        <CapturedLive
          capturedLabel="Show captured diagnosis"
          liveLabel="Run live diagnosis"
          onCaptured={runDiagnosis("captured")}
          onLive={runDiagnosis("live")}
          pending={diag.pending}
          liveAvailable={liveOK}
          caption="Both run the same versioned task module. The left returns a previously captured real run; the right calls the model now."
        />
        {diag.error && <p className="mt-4 text-danger">{diag.error}</p>}

        {d && (
          <div className="mt-6 space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={d.verdict === "failure" ? "danger" : "ok"} dot>
                {d.verdict === "failure" ? "real failure" : "expected behaviour"}
              </Badge>
              <Badge tone="neutral">{KIND_LABEL[d.remediation_kind] ?? d.remediation_kind}</Badge>
              <Badge tone="neutral">{d.confidence} confidence</Badge>
            </div>

            {d.verdict === "expected_behaviour" && (
              <p className="rounded-lg border border-ok/40 bg-ok/5 p-4 leading-relaxed text-secondary">
                Clustering groups traces by behaviour — it cannot tell a problem from a rare but
                correct one. This cluster was judged correct, so nothing is proposed for it. A
                system that produced a remediation for every cluster would be manufacturing work.
              </p>
            )}

            {sum ? (
              <div className="space-y-4 rounded-lg border border-hairline bg-surface-0 p-5">
                <p className="text-base leading-relaxed text-primary">{sum.headline}</p>
                <ol className="space-y-1.5">
                  {sum.what_happens.map((w, i) => (
                    <li key={i} className="flex gap-3 leading-relaxed text-secondary">
                      <span className="shrink-0 font-mono text-muted">{i + 1}</span>
                      <span>{w}</span>
                    </li>
                  ))}
                </ol>
                <div className="grid gap-4 border-t border-hairline pt-4 md:grid-cols-2">
                  <Field label="why it matters" body={sum.why_it_matters} />
                  <Field
                    label={d.verdict === "failure" ? "the fix, in one line" : "conclusion"}
                    body={sum.fix_in_one_line}
                  />
                </div>
                <p className="text-xs text-muted">
                  Summarised from the full diagnosis below by {sum.provenance.model} — no new
                  claims, nothing the analysis did not already say.
                </p>
              </div>
            ) : (
              <Field
                label={d.verdict === "failure" ? "Root cause" : "What this is"}
                body={d.root_cause}
              />
            )}

            <div className="space-y-2">
              {sum && <Detail label="Root cause — the full analysis" body={d.root_cause} />}
              <Detail label="How it happens, step by step" body={d.mechanism} />
              <Detail label="Why it keeps happening" body={d.why_it_recurs} />
              <Detail label="What the fix would be" body={d.remediation_summary} />
            </div>

            <KeyValue
              columns={2}
              items={[
                { key: "cited", label: "cited traces", value: d.cited_trace_ids.join(", "), mono: true },
                { key: "kind", label: "remediation", value: KIND_LABEL[d.remediation_kind] ?? d.remediation_kind },
              ]}
            />
          </div>
        )}
      </Card>

      {d && (
        <div className="flex flex-col items-start gap-3 border-t border-hairline pt-8">
          {d.verdict === "expected_behaviour" ? (
            <>
              <Button size="lg" variant="secondary" onClick={() => nav("/discovery")}>
                ← Back to patterns
              </Button>
              <p className="text-muted">
                Nothing to improve here. Pick another pattern.
              </p>
            </>
          ) : (
            <>
              <Button size="lg" variant="progress" onClick={() => nav(`/patterns/${patternId}/improve`)}>
                Improve this pattern →
              </Button>
              <p className="text-muted">
                {d.remediation_kind === "config"
                  ? "Generates a configuration patch, replays it against the frozen world, and gates it before promotion."
                  : "This one cannot be fixed by configuration, so the next step is a written proposal rather than an automatic change."}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The full analysis, one click away.
 *
 * The captured diagnosis runs to a couple of thousand characters. None of it is
 * cut — but on arrival it hid the finding, so the long form now opens on demand
 * underneath the summary.
 */
function Detail({ label, body }: { label: string; body: string }) {
  return (
    <details className="group rounded-lg border border-hairline bg-surface-0">
      <summary className="cursor-pointer select-none px-4 py-3 text-secondary hover:text-primary">
        <span className="mr-2 inline-block text-muted transition-transform group-open:rotate-90">
          &#9656;
        </span>
        {label}
      </summary>
      <p className="whitespace-pre-line px-4 pb-4 pl-10 leading-relaxed text-secondary">{body}</p>
    </details>
  );
}

function Field({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div className="mb-2 text-xs uppercase tracking-wide text-muted">{label}</div>
      <p className="leading-relaxed text-secondary">{body}</p>
    </div>
  );
}

export default Investigate;
