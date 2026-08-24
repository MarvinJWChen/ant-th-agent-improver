import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  ButtonPair,
  Card,
  CodeBlock,
  DiffView,
  EmptyState,
  GateChecklist,
  JourneyStepper,
  KeyValue,
  ProvenanceBadge,
  SectionHeading,
  Spinner,
  SplitPane,
  StatTile,
  Table,
  Timeline,
  type BadgeTone,
  type ButtonVariant,
  type GateCheck,
  type KeyValueItem,
  type ProvenanceHash,
  type TableColumn,
  type TimelineItem,
} from "../components";

function GallerySection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="mb-10">
      <SectionHeading title={title} subtitle={description} size="sm" />
      <div className="mt-3">{children}</div>
    </section>
  );
}

// --- sample domain data -----------------------------------------------

interface PatternRow {
  id: string;
  label: string;
  family: string;
  frequency: number;
  severity: "ok" | "warn" | "danger";
}

const PATTERN_ROWS: PatternRow[] = [
  { id: "pat_001", label: "Double refund on retry", family: "cluster-a", frequency: 34, severity: "danger" },
  { id: "pat_002", label: "Duplicate confirmation email", family: "cluster-b", frequency: 21, severity: "warn" },
  { id: "pat_003", label: "Premature escalation", family: "cluster-c", frequency: 18, severity: "warn" },
  { id: "pat_004", label: "Slow order lookup chain", family: "generic_latency", frequency: 9, severity: "ok" },
  { id: "pat_005", label: "Ambiguous refund_status read", family: "generic_ambiguous_tool", frequency: 6, severity: "ok" },
];

const SEVERITY_TONE: Record<PatternRow["severity"], BadgeTone> = { ok: "info", warn: "warn", danger: "danger" };

const PATTERN_COLUMNS: TableColumn<PatternRow>[] = [
  { key: "id", header: "Pattern", render: (r) => <span className="font-mono text-xs text-secondary">{r.id}</span> },
  { key: "label", header: "Description" },
  { key: "family", header: "Family", render: (r) => <span className="font-mono text-xs text-muted">{r.family}</span> },
  {
    key: "severity",
    header: "Severity",
    render: (r) => (
      <Badge tone={SEVERITY_TONE[r.severity]} dot>
        {r.severity}
      </Badge>
    ),
  },
  { key: "frequency", header: "Traces", numeric: true, sortable: true, sortValue: (r) => r.frequency },
];

const TIMELINE_ITEMS: TimelineItem[] = [
  { id: "e1", seq: 1, type: "user_msg", title: "“I want a refund for order ord_10233”" },
  { id: "e2", seq: 2, type: "model_turn", title: "Plans lookup + refund_status check", latencyMs: 640 },
  {
    id: "e3",
    seq: 3,
    type: "tool_call",
    title: "order_lookup({ order_id: \"ord_10233\" })",
    payload: '{\n  "order_id": "ord_10233"\n}',
    latencyMs: 120,
  },
  {
    id: "e4",
    seq: 4,
    type: "tool_result",
    title: "order_lookup -> delivered, $84.00",
    payload: '{\n  "status": "delivered",\n  "amount_cents": 8400\n}',
    latencyMs: 20,
  },
  {
    id: "e5",
    seq: 5,
    type: "tool_call",
    title: "refund_execute({ order_id, amount_cents: 8400 })",
    payload: '{\n  "order_id": "ord_10233",\n  "amount_cents": 8400\n}',
    latencyMs: 2380,
    highlight: true,
  },
  { id: "e6", seq: 6, type: "tool_result", title: "refund_execute -> timeout, retried by model", error: "timeout", latencyMs: 3010, highlight: true },
  { id: "e7", seq: 7, type: "tool_call", title: "refund_execute({ order_id, amount_cents: 8400 }) — retry", latencyMs: 340, highlight: true },
  { id: "e8", seq: 8, type: "agent_msg", title: "“Your refund of $84.00 has been processed.”", dim: true },
];

const CONFIG_DIFF = `--- a/configs/v1/system_prompt.txt
+++ b/configs/v2-candidate-a/system_prompt.txt
@@ -10,8 +10,9 @@
 Tools available:
-- refund_status(order_id): returns status.
+- refund_status(order_id): returns the CURRENT refund status for an order.
+  Always call this immediately before refund_execute to avoid issuing a
+  duplicate refund on retry.
 - refund_execute(order_id, amount_cents): executes a refund.
-- send_email(customer_id, template, order_id): sends a templated email.
+- send_email(customer_id, template, order_id, idempotency_key): sends a
+  templated email. idempotency_key is required.
`;

const PATCH_JSON = `{
  "version": "v2-candidate-a",
  "parent_version": "v1",
  "model": "claude-opus-4-6",
  "tools_changed": ["refund_status", "send_email"],
  "notes": "Disambiguate refund_status; require send_email idempotency_key"
}`;

const HASHES: ProvenanceHash[] = [
  { label: "config_hash", value: "sha256:9f2c4a7e1b3d0e8f6a5c2b9d4e1f0a3c7b6d9e2f1a4c8b0d3e6f9a2c5b8d1e4f" },
  { label: "world_hash", value: "sha256:1a4c8b0d3e6f9a2c5b8d1e4f9f2c4a7e1b3d0e8f6a5c2b9d4e1f0a3c7b6d9e2f" },
  { label: "trace_id", value: "tr_000412" },
];

const GATE_CHECKS: GateCheck[] = [
  { id: "no_unsafe_effects", label: "Zero unsafe external effects", status: "pass", detail: "0 real refund_execute / send_email calls in replay" },
  { id: "target_metric", label: "Target metric improved", status: "pass", detail: "Double-refund rate 3.4% -> 0.2%" },
  { id: "controls_pass", label: "Control traces still pass", status: "pass", detail: "412/412 unaffected traces unchanged" },
  { id: "escalation_regression", label: "No escalation-rate regression", status: "pending", detail: "Awaiting second replay batch" },
];

const GATE_CHECKS_BLOCKED: GateCheck[] = [
  { id: "no_unsafe_effects", label: "Zero unsafe external effects", status: "pass" },
  { id: "duplicate_refunds", label: "Duplicate refund count == 0", status: "fail", detail: "2 duplicate refund_execute calls remain in replay" },
];

const BASELINE_CONFIG_ITEMS: KeyValueItem[] = [
  { key: "version", label: "version", value: "v1" },
  { key: "model", label: "model", value: "claude-opus-4-6" },
  { key: "status", label: "status", value: "active" },
  { key: "config_hash", label: "config_hash", value: "sha256:9f2c4a7e1b3d0e8f6a5c2b9d4e1f0a3c", truncateMiddle: true },
];

const CANDIDATE_CONFIG_ITEMS: KeyValueItem[] = [
  { key: "version", label: "version", value: "v2-candidate-a" },
  { key: "model", label: "model", value: "claude-opus-4-6" },
  { key: "status", label: "status", value: "candidate" },
  { key: "config_hash", label: "config_hash", value: "sha256:1a4c8b0d3e6f9a2c5b8d1e4f9f2c4a7e", truncateMiddle: true },
];

const VARIANTS: ButtonVariant[] = ["primary", "secondary", "ghost", "danger"];

/**
 * Component gallery — every kit component with representative props. This is
 * the lead engineer's acceptance test for the kit: `/kit`.
 */
export function Kit() {
  const [selectedPatternId, setSelectedPatternId] = useState<string | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SectionHeading
        title="Component kit"
        subtitle="Every reusable component with representative props — the acceptance test for /apps/web's shared kit."
      />

      <GallerySection title="JourneyStepper" description="4 states: completed / current / upcoming / locked">
        <div className="flex flex-col gap-3 overflow-hidden rounded-md border border-hairline">
          <JourneyStepper currentStepId="diagnose" activePatternId="pat_001" />
          <JourneyStepper
            currentStepId="replay"
            activePatternId="pat_001"
            statuses={{ overview: "completed", discovery: "completed", diagnose: "completed", replay: "current", proposals: "locked" }}
          />
        </div>
      </GallerySection>

      <GallerySection title="Card" description="titled surface with subtitle, right slot, and footer">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card title="Pattern pat_001" subtitle="Double refund on retry" right={<Badge tone="danger">34 traces</Badge>}>
            <p className="text-sm text-secondary">
              Diagnosed root cause: <code className="font-mono text-xs text-primary">refund_status</code> description is
              ambiguous about staleness, so the model re-issues <code className="font-mono text-xs text-primary">refund_execute</code>
              {" "}after a timeout instead of checking status first.
            </p>
          </Card>
          <Card
            title="Replay summary"
            subtitle="v2-candidate-a vs v1"
            footer={
              <div className="flex justify-end">
                <Button variant="primary" size="sm">
                  Promote candidate
                </Button>
              </div>
            }
          >
            <p className="text-sm text-secondary">412 control traces replayed with zero behavior change.</p>
          </Card>
        </div>
      </GallerySection>

      <GallerySection title="StatTile" description="big monospace number, label, optional delta and sublabel">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Traces analyzed" value="1,000" delta={{ value: "+120", direction: "up" }} sublabel="last 24h" />
          <StatTile label="Failure patterns" value="7" delta={{ value: "0", direction: "flat" }} sublabel="clustered" />
          <StatTile
            label="P50 latency"
            value="842ms"
            delta={{ value: "-96ms", direction: "down", tone: "ok" }}
            sublabel="candidate vs baseline"
          />
          <StatTile
            label="Escalation rate"
            value="4.2%"
            delta={{ value: "+1.1pp", direction: "up", tone: "danger" }}
            sublabel="needs review"
          />
        </div>
      </GallerySection>

      <GallerySection title="Button" description="variants x sizes, loading, disabled with tooltip">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {VARIANTS.map((variant) => (
              <Button key={`${variant}-md`} variant={variant} size="md">
                {variant}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {VARIANTS.map((variant) => (
              <Button key={`${variant}-sm`} variant={variant} size="sm">
                {variant} sm
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" loading={isLoading} onClick={() => setIsLoading((v) => !v)}>
              {isLoading ? "Running replay…" : "Toggle loading"}
            </Button>
            <Button variant="secondary" disabled title="Requires an approved diagnosis first">
              Generate patch (disabled)
            </Button>
          </div>
        </div>
      </GallerySection>

      <GallerySection title="ButtonPair" description="two actions sharing one border — captured vs live">
        <div className="flex flex-col gap-4 sm:flex-row">
          <ButtonPair
            left={{ label: "Replay captured", onClick: () => {} }}
            right={{ label: "Replay live", onClick: () => {}, disabled: true, disabledReason: "No ANTHROPIC_API_KEY configured" }}
            caption="Captured replays instantly against the frozen world snapshot; live reruns the diagnosis LLM."
          />
          <ButtonPair
            size="sm"
            left={{ label: "View fixture", onClick: () => {} }}
            right={{ label: "Refresh", onClick: () => {}, loading: true }}
          />
        </div>
      </GallerySection>

      <GallerySection title="Badge" description="tone x dot x mono">
        <div className="flex flex-wrap items-center gap-2">
          {(["neutral", "ok", "warn", "danger", "info", "accent"] as BadgeTone[]).map((tone) => (
            <Badge key={tone} tone={tone} dot>
              {tone}
            </Badge>
          ))}
          <Badge tone="ok" mono>
            v2-candidate-a
          </Badge>
        </div>
      </GallerySection>

      <GallerySection title="Table" description="generic columns, sortable, sticky header, monospace numerics, onRowClick">
        <Table
          columns={PATTERN_COLUMNS}
          rows={PATTERN_ROWS}
          rowKey={(r) => r.id}
          onRowClick={(r) => setSelectedPatternId(r.id)}
          initialSortKey="frequency"
          initialSortDir="desc"
          maxHeightClassName="max-h-72"
        />
        <p className="mt-2 text-xs text-muted">
          Selected row: <span className="font-mono text-secondary">{selectedPatternId ?? "none"}</span>
        </p>
      </GallerySection>

      <GallerySection title="Timeline" description="sequence, type, collapsible payload, latency/error chips, highlight/dim">
        <Card noPadding>
          <div className="p-4">
            <Timeline items={TIMELINE_ITEMS} />
          </div>
        </Card>
      </GallerySection>

      <GallerySection title="DiffView" description="unified diff — line numbers, add/remove backgrounds, own h-scroll">
        <DiffView diff={CONFIG_DIFF} filename="configs/system_prompt.txt" />
      </GallerySection>

      <GallerySection title="CodeBlock" description="monospace, overflow-x-auto, optional filename header">
        <CodeBlock code={PATCH_JSON} filename="patch_v2-candidate-a.json" language="json" />
      </GallerySection>

      <GallerySection title="KeyValue" description="dense definition list, monospace values, truncateMiddle for hashes">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card title="Baseline (v1)" noPadding bodyClassName="p-4">
            <KeyValue items={BASELINE_CONFIG_ITEMS} />
          </Card>
          <Card title="Candidate (v2-candidate-a)" noPadding bodyClassName="p-4">
            <KeyValue items={CANDIDATE_CONFIG_ITEMS} />
          </Card>
        </div>
      </GallerySection>

      <GallerySection title="GateChecklist" description="overall verdict header derived from check statuses">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <GateChecklist checks={GATE_CHECKS} />
          <GateChecklist checks={GATE_CHECKS_BLOCKED} title="Promotion gate — blocked example" />
        </div>
      </GallerySection>

      <GallerySection title="SplitPane" description="labelled two-column comparison, stacks below md">
        <SplitPane
          leftLabel="Baseline v1"
          rightLabel="Candidate v2-candidate-a"
          leftMeta={<Badge tone="neutral">active</Badge>}
          rightMeta={<Badge tone="accent">candidate</Badge>}
          left={<CodeBlock code={'refund_status(order_id): returns status.'} language="txt" />}
          right={<CodeBlock code={'refund_status(order_id): returns the CURRENT\nrefund status. Call before refund_execute.'} language="txt" />}
        />
      </GallerySection>

      <GallerySection title="ProvenanceBadge" description="source x verification, expands to a KeyValue of hashes on click">
        <div className="flex flex-wrap items-start gap-3">
          <ProvenanceBadge source="captured" verification="verified" hashes={HASHES} />
          <ProvenanceBadge source="live" verification="stale" />
          <ProvenanceBadge source="live" verification="unverified" hashes={HASHES.slice(0, 1)} />
        </div>
      </GallerySection>

      <GallerySection title="Spinner" description="xs / sm / md">
        <div className="flex items-center gap-4">
          <Spinner size="xs" />
          <Spinner size="sm" />
          <Spinner size="md" />
        </div>
      </GallerySection>

      <GallerySection title="EmptyState" description="with and without an action">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <EmptyState title="No patterns discovered yet" description="Run discovery to cluster recurring failures across the 1,000 traces." />
          <EmptyState
            title="No candidate promoted"
            description="Diagnose a pattern and pass the replay gate to generate a promotable proposal."
            action={
              <Button variant="primary" size="sm">
                Go to Discovery
              </Button>
            }
          />
        </div>
      </GallerySection>

      <GallerySection title="SectionHeading" description="used throughout this page as the section header">
        <SectionHeading
          title="Example heading"
          subtitle="With a subtitle and a right-aligned action slot"
          right={<Badge tone="accent">example</Badge>}
        />
      </GallerySection>
    </div>
  );
}

export default Kit;
