/**
 * Typed client for the Agent Improver API.
 *
 * Shapes mirror apps/api/contracts.py. Every model-dependent endpoint takes an
 * explicit mode — there is no ambient "demo mode" toggle, because the person
 * watching should always be able to see which button produced the panel.
 */

export type Mode = "captured" | "live";
export type RemediationKind = "config" | "code" | "process" | "none";

export interface ToolDef {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  effect_class: "read" | "shadow_write" | "external" | "unknown";
}

export interface AgentConfig {
  version: string;
  created_at: string;
  model: string;
  system_prompt: string;
  tools: ToolDef[];
  config_hash: string;
  status: string;
  parent_version?: string | null;
  notes?: string | null;
}

export interface CorpusStats {
  total_traces: number;
  total_events: number;
  window_start: string;
  window_end: string;
  outcome_counts: Record<string, number>;
  intent_counts: Record<string, number>;
  p50_duration_ms: number;
  p95_duration_ms: number;
  escalation_rate: number;
  resolution_rate: number;
}

export interface AgentOverview {
  agent_name: string;
  active_config: AgentConfig;
  corpus: CorpusStats;
  live_available: boolean;
}

export interface TraceSummary {
  trace_id: string;
  ts: string;
  customer_id: string;
  order_id: string;
  intent: string;
  duration_ms: number;
  turns: number;
  outcome: string;
  summary: string;
}

export interface TraceEvent {
  seq: number;
  type: string;
  tool_name?: string | null;
  args?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  latency_ms: number;
  error?: string | null;
  content?: string | null;
}

export interface TraceDetail extends TraceSummary {
  config_version: string;
  events: TraceEvent[];
}

export interface EvidenceHit {
  source: "evaluator" | "anomaly";
  rule_id?: string | null;
  label: string;
  detail: string;
  score?: number | null;
}

export interface FlaggedTrace {
  trace: TraceSummary;
  hits: EvidenceHit[];
  anomaly_score: number;
  rule_flagged: boolean;
  cluster_id?: number | null;
}

export interface PatternCard {
  pattern_id: string;
  title: string;
  signature: string;
  size: number;
  share_of_flagged: number;
  discovered_by: "evaluator+anomaly" | "anomaly-only";
  remediation_kind?: RemediationKind | null;
  verdict?: "failure" | "expected_behaviour" | null;
  top_features: string[];
  exemplar_trace_ids: string[];
  representative_evidence: string[];
  /** the trace each evidence line came from, positionally */
  evidence_trace_ids: string[];
  impact: Record<string, number | string>;
}

export interface DiscoveryResult {
  computed_at: string;
  corpus_hash: string;
  n_traces_scanned: number;
  n_flagged: number;
  n_rule_flagged: number;
  n_anomaly_only: number;
  anomaly_threshold: number;
  cluster_k: number;
  silhouette: number;
  patterns: PatternCard[];
  flagged: FlaggedTrace[];
}

export interface Provenance {
  mode: Mode;
  task: string;
  task_version: string;
  model: string;
  created_at: string;
  verified: boolean;
  stale_reason?: string | null;
  hashes: Record<string, string>;
  expected_hashes?: Record<string, string> | null;
  latency_ms?: number | null;
}

export interface Diagnosis {
  pattern_id: string;
  verdict: "failure" | "expected_behaviour";
  root_cause: string;
  mechanism: string;
  why_it_recurs: string;
  cited_trace_ids: string[];
  confidence: "low" | "medium" | "high";
  remediation_kind: RemediationKind;
  remediation_summary: string;
}

export interface DiagnosisSummary {
  headline: string;
  what_happens: string[];
  why_it_matters: string;
  fix_in_one_line: string;
  provenance: Provenance;
}

export interface DiagnosisResponse {
  diagnosis: Diagnosis;
  provenance: Provenance;
  /** scannable compression of the diagnosis; absent when no capture exists */
  summary?: DiagnosisSummary | null;
}

export interface ConfigPatch {
  system_prompt_before: string;
  system_prompt_after: string;
  tool_description_edits: { tool_name: string; before: string; after: string }[];
  rationale: string;
  expected_effect: string;
  risks: string[];
}

export interface PatchCandidate {
  candidate_version: string;
  parent_version: string;
  config_hash: string;
  patch: ConfigPatch;
  within_edit_boundary: boolean;
  boundary_report: string[];
  label: string;
}

export interface PatchResponse {
  candidates: PatchCandidate[];
  provenance: Provenance;
}

export interface ProposalResponse {
  kind: RemediationKind;
  code?: { file_path: string; unified_diff: string; rationale: string; test_note: string } | null;
  process?: {
    problem_statement: string;
    steps: { title: string; detail: string }[];
    owners: string[];
    metrics: string[];
    rationale: string;
  } | null;
  config?: ConfigPatch | null;
  provenance: Provenance;
  verdict?: "failure" | "expected_behaviour";
  explanation?: string;
}

export interface LedgerRow {
  seq: number;
  tool: string;
  effect_class: string;
  target: string;
  args_digest: string;
  disposition: "READ_FROM_CLONE" | "APPLIED_TO_CLONE" | "SHADOWED" | "BLOCKED_UNKNOWN_EFFECT";
  external: boolean;
  note?: string | null;
}

export interface ArmStep {
  seq: number;
  kind: string;
  tool_name?: string | null;
  args?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  text?: string | null;
  diverged: boolean;
}

export interface ArmRun {
  arm: "baseline" | "candidate";
  trace_id: string;
  clone_path: string;
  clone_sha256: string;
  clone_sha256_after: string;
  source_world_sha256: string;
  execution: "replayed" | "re-executed";
  steps: ArmStep[];
  ledger: LedgerRow[];
  unsafe_effects: number;
  external_calls_executed: number;
  outcome: string;
  turns: number;
}

export interface TracePair {
  trace_id: string;
  cohort: "target" | "control";
  baseline: ArmRun;
  candidate: ArmRun;
  trajectory_diverged: boolean;
  baseline_pass: boolean;
  candidate_pass: boolean;
  regression: boolean;
}

export interface ArmMetrics {
  double_refund_rate: number;
  duplicate_confirmation_rate: number;
  premature_escalation_rate: number;
  resolution_rate: number;
  avg_turns: number;
  unsafe_effects: number;
  external_calls_executed: number;
}

export interface GateCheckOut {
  id: string;
  label: string;
  status: "pass" | "fail" | "pending";
  detail: string;
  evidence: string[];
}

export interface GateResult {
  verdict: "pass" | "fail" | "pending";
  checks: GateCheckOut[];
  promotable: boolean;
}

export interface ReplayRun {
  run_id: string;
  pattern_id: string;
  candidate_version: string;
  baseline_version: string;
  mode: Mode;
  started_at: string;
  finished_at: string;
  cohort_target: string[];
  cohort_control: string[];
  world_isolation: Record<string, number | string>;
  baseline_metrics: ArmMetrics;
  candidate_metrics: ArmMetrics;
  pairs: TracePair[];
  gate: GateResult;
  provenance: Provenance;
  promoted: boolean;
}

export interface PromoteResponse {
  promoted: boolean;
  active_version: string;
  message: string;
  gate: GateResult;
}

export interface ResetResponse {
  reset: boolean;
  active_version: string;
  candidates_removed: number;
  replay_runs_cleared: number;
  clone_dirs_removed: number;
  message: string;
}

export interface Health {
  ok: boolean;
  live_available: boolean;
  subsystems: Record<string, string>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const post = <T,>(p: string) => req<T>(p, { method: "POST" });

export const api = {
  health: () => req<Health>("/health"),
  agent: () => req<AgentOverview>("/agent"),
  configs: () => req<AgentConfig[]>("/configs"),
  traces: (limit = 25) => req<TraceSummary[]>(`/traces?limit=${limit}`),
  trace: (id: string) => req<TraceDetail>(`/traces/${id}`),
  discovery: () => req<DiscoveryResult>("/discovery"),
  runDiscovery: () => post<DiscoveryResult>("/discovery/run"),
  pattern: (id: string) =>
    req<{ pattern: PatternCard; flagged: FlaggedTrace[]; discovery_meta: Record<string, number | string> }>(
      `/patterns/${id}`,
    ),
  diagnose: (id: string, mode: Mode) => post<DiagnosisResponse>(`/patterns/${id}/diagnose?mode=${mode}`),
  propose: (id: string, mode: Mode) => post<ProposalResponse>(`/patterns/${id}/propose?mode=${mode}`),
  patch: (id: string, mode: Mode) => post<PatchResponse>(`/patterns/${id}/patch?mode=${mode}`),
  replay: (patternId: string, candidate: string, mode: Mode) =>
    post<ReplayRun>(`/replay/run?pattern_id=${patternId}&candidate_version=${candidate}&mode=${mode}`),
  replayGet: (runId: string) => req<ReplayRun>(`/replay/${runId}`),
  promote: (runId: string) => post<PromoteResponse>(`/replay/${runId}/promote`),
  resetDemo: () => post<ResetResponse>("/demo/reset"),
};

export function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function pct(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}
