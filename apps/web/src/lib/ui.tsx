import { useEffect, useState } from "react";
import { ButtonPair, EmptyState, Spinner } from "../components";
import type { Provenance, TraceDetail } from "./api";
import type { TimelineItem } from "../components";

export function Loading({ label }: { label: string }) {
  return (
    <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-24 text-muted">
      <Spinner /> {label}…
    </div>
  );
}

export function Failed({ message }: { message: string }) {
  return (
    <div className="mx-auto max-w-5xl px-6 py-16">
      <EmptyState title="Request failed" description={message} />
    </div>
  );
}

/** Map an API Provenance onto the badge component's props. */
export function provenanceProps(p: Provenance) {
  return {
    source: p.mode,
    verification: (p.mode === "live" ? "verified" : p.verified ? "verified" : "stale") as
      | "verified"
      | "stale",
    hashes: Object.entries(p.hashes).map(([label, value]) => ({ label, value })),
  };
}

const TOOL_OF_INTEREST = new Set(["refund_execute", "escalate_to_human"]);

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
    highlight: (e.tool_name != null && TOOL_OF_INTEREST.has(e.tool_name)) || e.type === "escalation",
  }));
}

/** Human label for a remediation kind. */
export const KIND_LABEL: Record<string, string> = {
  config: "Agent configuration",
  code: "Tool code change",
  process: "Operational change",
  none: "No change needed",
};

/* ------------------------------------------------------------------ live runs */

export interface CapturedLiveProps {
  capturedLabel: string;
  liveLabel: string;
  onCaptured: () => void;
  onLive: () => void;
  pending: string | null;
  liveAvailable: boolean;
  caption?: string;
  /** rough wall-clock for a live call, used to set expectations before the click */
  liveSeconds?: number;
}

/**
 * The captured/live control.
 *
 * A live call is a real model request that takes tens of seconds and costs
 * money, so it is deliberately not as inviting as the captured default: it arms
 * on the first click and only runs on the second, and it shows elapsed time
 * while it works so a long pause never looks like a hang.
 */
export function CapturedLive({
  capturedLabel,
  liveLabel,
  onCaptured,
  onLive,
  pending,
  liveAvailable,
  caption,
  liveSeconds = 30,
}: CapturedLiveProps) {
  const [armed, setArmed] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const running = pending === "live";

  useEffect(() => {
    if (!running) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 6000);
    return () => clearTimeout(t);
  }, [armed]);

  return (
    <div className="space-y-2">
      <ButtonPair
        size="lg"
        left={{
          label: capturedLabel,
          loading: pending === "captured",
          onClick: onCaptured,
        }}
        right={{
          label: running
            ? `Running… ${elapsed}s`
            : armed
              ? `Confirm — runs the model now (~${liveSeconds}s)`
              : liveLabel,
          loading: running,
          disabled: !liveAvailable,
          disabledReason: "No ANTHROPIC_API_KEY is configured on this deployment.",
          onClick: () => {
            if (armed) {
              setArmed(false);
              onLive();
            } else {
              setArmed(true);
            }
          },
        }}
        caption={caption}
      />
    </div>
  );
}
