"""API response contracts.

These shapes are frozen early on purpose: the browser journey is built against
them with fixtures, then each field is progressively backed by a real
implementation without the frontend changing. See SCHEMA.md for storage.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Mode = Literal["captured", "live"]
Family = Literal["config", "code", "process"]
Disposition = Literal[
    "READ_FROM_CLONE",
    "APPLIED_TO_CLONE",
    "SHADOWED",
    "BLOCKED_UNKNOWN_EFFECT",
]
EffectClass = Literal["read", "shadow_write", "external", "unknown"]


# ---------------------------------------------------------------- agent / corpus


class ToolDef(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    effect_class: EffectClass


class AgentConfigOut(BaseModel):
    version: str
    created_at: str
    model: str
    system_prompt: str
    tools: list[ToolDef]
    config_hash: str
    status: str
    parent_version: str | None = None
    notes: str | None = None


class CorpusStats(BaseModel):
    total_traces: int
    total_events: int
    window_start: str
    window_end: str
    outcome_counts: dict[str, int]
    intent_counts: dict[str, int]
    p50_duration_ms: int
    p95_duration_ms: int
    escalation_rate: float
    resolution_rate: float


class AgentOverview(BaseModel):
    agent_name: str
    active_config: AgentConfigOut
    corpus: CorpusStats
    live_available: bool


# ---------------------------------------------------------------- traces


class TraceEvent(BaseModel):
    seq: int
    type: str
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    latency_ms: int = 0
    error: str | None = None
    content: str | None = None


class TraceSummary(BaseModel):
    trace_id: str
    ts: str
    customer_id: str
    order_id: str
    intent: str
    duration_ms: int
    turns: int
    outcome: str
    summary: str


class TraceDetail(TraceSummary):
    config_version: str
    events: list[TraceEvent]


# ---------------------------------------------------------------- discovery


class EvidenceHit(BaseModel):
    """Why a trace was flagged. Rule hits carry a citation; anomaly hits carry a score."""

    source: Literal["evaluator", "anomaly"]
    rule_id: str | None = None
    label: str
    detail: str
    score: float | None = None


class FlaggedTrace(BaseModel):
    trace: TraceSummary
    hits: list[EvidenceHit]
    anomaly_score: float
    rule_flagged: bool
    cluster_id: int | None = None


class PatternCard(BaseModel):
    pattern_id: str
    title: str
    signature: str
    size: int
    share_of_flagged: float
    discovered_by: Literal["evaluator+anomaly", "anomaly-only"]
    # Deliberately unset until an LLM diagnosis classifies it. The clusterer
    # groups behaviour; it has no basis for asserting the kind of fix required.
    remediation_kind: Family | None = None
    top_features: list[str]
    exemplar_trace_ids: list[str]
    representative_evidence: list[str]
    impact: dict[str, Any]


class DiscoveryResult(BaseModel):
    computed_at: str
    corpus_hash: str
    n_traces_scanned: int
    n_flagged: int
    n_rule_flagged: int
    n_anomaly_only: int
    anomaly_threshold: float
    cluster_k: int
    silhouette: float
    patterns: list[PatternCard]
    flagged: list[FlaggedTrace]


# ---------------------------------------------------------------- provenance / LLM


class Provenance(BaseModel):
    mode: Mode
    task: str
    task_version: str
    model: str
    created_at: str
    verified: bool
    stale_reason: str | None = None
    hashes: dict[str, str]
    expected_hashes: dict[str, str] | None = None
    latency_ms: int | None = None


class Diagnosis(BaseModel):
    pattern_id: str
    root_cause: str
    mechanism: str
    why_it_recurs: str
    cited_trace_ids: list[str]
    confidence: Literal["low", "medium", "high"]
    remediation_kind: Family
    remediation_summary: str


class DiagnosisResponse(BaseModel):
    diagnosis: Diagnosis
    provenance: Provenance


class ToolDescriptionEdit(BaseModel):
    tool_name: str
    before: str
    after: str


class ConfigPatch(BaseModel):
    system_prompt_before: str
    system_prompt_after: str
    tool_description_edits: list[ToolDescriptionEdit]
    rationale: str
    expected_effect: str
    risks: list[str]


class PatchCandidate(BaseModel):
    candidate_version: str
    parent_version: str
    config_hash: str
    patch: ConfigPatch
    within_edit_boundary: bool
    boundary_report: list[str]
    label: str


class PatchResponse(BaseModel):
    candidates: list[PatchCandidate]
    provenance: Provenance


class CodeProposal(BaseModel):
    file_path: str
    unified_diff: str
    rationale: str
    test_note: str


class ProcessProposal(BaseModel):
    problem_statement: str
    steps: list[dict[str, str]]
    owners: list[str]
    metrics: list[str]
    rationale: str


class ProposalResponse(BaseModel):
    kind: Family
    code: CodeProposal | None = None
    process: ProcessProposal | None = None
    config: ConfigPatch | None = None
    provenance: Provenance


# ---------------------------------------------------------------- replay


class LedgerRow(BaseModel):
    seq: int
    tool: str
    effect_class: EffectClass
    target: str
    args_digest: str
    disposition: Disposition
    external: bool
    note: str | None = None


class ArmTrajectoryStep(BaseModel):
    seq: int
    kind: Literal["model_turn", "tool_call", "tool_result", "agent_msg", "escalation"]
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    text: str | None = None
    diverged: bool = False


class ArmRun(BaseModel):
    arm: Literal["baseline", "candidate"]
    trace_id: str
    clone_path: str
    clone_sha256: str          # at creation — identical across arms, proving the same start
    clone_sha256_after: str    # after the arm ran — differs when effects differed
    source_world_sha256: str
    execution: Literal["replayed", "re-executed"]
    steps: list[ArmTrajectoryStep]
    ledger: list[LedgerRow]
    unsafe_effects: int
    external_calls_executed: int
    outcome: str
    turns: int


class TracePairResult(BaseModel):
    trace_id: str
    cohort: Literal["target", "control"]
    baseline: ArmRun
    candidate: ArmRun
    trajectory_diverged: bool
    baseline_pass: bool
    candidate_pass: bool
    regression: bool


class ArmMetrics(BaseModel):
    double_refund_rate: float
    duplicate_confirmation_rate: float
    premature_escalation_rate: float
    resolution_rate: float
    avg_turns: float
    unsafe_effects: int
    external_calls_executed: int


class GateCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "fail", "pending"]
    detail: str
    evidence: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    verdict: Literal["pass", "fail", "pending"]
    checks: list[GateCheck]
    promotable: bool


class ReplayRun(BaseModel):
    run_id: str
    pattern_id: str
    candidate_version: str
    baseline_version: str
    mode: Mode
    started_at: str
    finished_at: str
    cohort_target: list[str]
    cohort_control: list[str]
    world_isolation: dict[str, Any]
    baseline_metrics: ArmMetrics
    candidate_metrics: ArmMetrics
    pairs: list[TracePairResult]
    gate: GateResult
    provenance: Provenance
    promoted: bool = False


class PromoteResponse(BaseModel):
    promoted: bool
    active_version: str
    message: str
    gate: GateResult
