import { useState } from "react";
import { cn } from "../lib/utils";
import { TONE, type Tone } from "../lib/tone";
import { KeyValue } from "./KeyValue";

export type ProvenanceSource = "captured" | "live";
export type ProvenanceVerification = "verified" | "stale" | "unverified";

export interface ProvenanceHash {
  label: string;
  value: string;
}

export interface ProvenanceBadgeProps {
  source: ProvenanceSource;
  verification: ProvenanceVerification;
  /** hashes shown in the expanded KeyValue detail (e.g. config_hash, world_hash) */
  hashes?: ProvenanceHash[];
  /** start expanded */
  defaultExpanded?: boolean;
  className?: string;
}

const SOURCE_META: Record<ProvenanceSource, { label: string; tone: Tone }> = {
  captured: { label: "Captured", tone: "neutral" },
  live: { label: "Live", tone: "info" },
};

const VERIFICATION_META: Record<ProvenanceVerification, { label: string; tone: Tone }> = {
  verified: { label: "Verified", tone: "ok" },
  stale: { label: "Stale", tone: "warn" },
  unverified: { label: "Unverified", tone: "danger" },
};

/** Compact source + verification badge; expands on click to a KeyValue of provenance hashes. */
export function ProvenanceBadge({
  source,
  verification,
  hashes,
  defaultExpanded = false,
  className,
}: ProvenanceBadgeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const sourceMeta = SOURCE_META[source];
  const verificationMeta = VERIFICATION_META[verification];
  const hasDetail = !!hashes && hashes.length > 0;

  return (
    <div className={cn("inline-flex flex-col", className)}>
      <button
        type="button"
        onClick={() => hasDetail && setExpanded((e) => !e)}
        aria-expanded={hasDetail ? expanded : undefined}
        disabled={!hasDetail}
        className={cn(
          "inline-flex items-center gap-1.5 rounded border border-hairline bg-surface-2 px-2 py-1 font-mono text-xs transition-colors duration-120",
          hasDetail ? "cursor-pointer hover:border-hairline-strong" : "cursor-default",
        )}
      >
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", TONE[verificationMeta.tone].dot)} aria-hidden />
        <span className={cn("uppercase tracking-wide", TONE[sourceMeta.tone].text)}>{sourceMeta.label}</span>
        <span className="text-muted">/</span>
        <span className={TONE[verificationMeta.tone].text}>{verificationMeta.label}</span>
        {hasDetail && (
          <span className="text-muted" aria-hidden>
            {expanded ? "▴" : "▾"}
          </span>
        )}
      </button>
      {expanded && hasDetail && (
        <div className="mt-1.5 rounded border border-hairline bg-surface-2 p-2.5">
          <KeyValue
            items={hashes!.map((h) => ({ key: h.label, label: h.label, value: h.value, truncateMiddle: true }))}
          />
        </div>
      )}
    </div>
  );
}
