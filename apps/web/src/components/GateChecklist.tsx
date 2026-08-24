import { cn } from "../lib/utils";
import { TONE, type Tone } from "../lib/tone";
import { Badge } from "./Badge";

export type GateCheckStatus = "pass" | "fail" | "pending";
export type GateVerdict = "pass" | "fail" | "pending";

export interface GateCheck {
  id: string;
  label: string;
  status: GateCheckStatus;
  detail?: string;
}

export interface GateChecklistProps {
  checks: GateCheck[];
  /** overall verdict; derived from `checks` when omitted (any fail -> fail, else any pending -> pending, else pass) */
  verdict?: GateVerdict;
  title?: string;
  className?: string;
}

const STATUS_META: Record<GateCheckStatus, { glyph: string; tone: Tone }> = {
  pass: { glyph: "✓", tone: "ok" },
  fail: { glyph: "✕", tone: "danger" },
  pending: { glyph: "…", tone: "warn" },
};

const VERDICT_META: Record<GateVerdict, { label: string; tone: Tone }> = {
  pass: { label: "Gate: pass", tone: "ok" },
  fail: { label: "Gate: blocked", tone: "danger" },
  pending: { label: "Gate: pending", tone: "warn" },
};

export function deriveGateVerdict(checks: GateCheck[]): GateVerdict {
  if (checks.some((c) => c.status === "fail")) return "fail";
  if (checks.some((c) => c.status === "pending")) return "pending";
  return "pass";
}

export function GateChecklist({ checks, verdict, title = "Promotion gate", className }: GateChecklistProps) {
  const resolved = verdict ?? deriveGateVerdict(checks);
  const vm = VERDICT_META[resolved];
  const passCount = checks.filter((c) => c.status === "pass").length;

  return (
    <div className={cn("overflow-hidden rounded-md border border-hairline bg-surface-2", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted">{title}</div>
          <div className={cn("mt-0.5 text-sm font-semibold", TONE[vm.tone].text)}>{vm.label}</div>
        </div>
        <Badge tone={vm.tone} mono>
          {passCount}/{checks.length} passed
        </Badge>
      </div>
      <ul className="divide-y divide-hairline">
        {checks.map((check) => {
          const meta = STATUS_META[check.status];
          return (
            <li key={check.id} className="flex items-start gap-3 px-4 py-2.5">
              <span
                className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border font-mono text-[10px]",
                  TONE[meta.tone].bg,
                  TONE[meta.tone].border,
                  TONE[meta.tone].text,
                )}
                aria-hidden
              >
                {meta.glyph}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm text-primary">{check.label}</div>
                {check.detail && <div className="mt-0.5 truncate text-xs text-muted">{check.detail}</div>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
