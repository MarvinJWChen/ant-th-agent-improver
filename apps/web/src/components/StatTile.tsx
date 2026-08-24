import { cn } from "../lib/utils";
import { TONE } from "../lib/tone";

export type DeltaDirection = "up" | "down" | "flat";

export interface StatTileDelta {
  value: string | number;
  direction: DeltaDirection;
  /**
   * Overrides the default semantic color. By default "up" reads as good (ok)
   * and "down" reads as bad (danger) — pass `tone` to flip that when a
   * decrease is the good outcome (e.g. latency, error rate).
   */
  tone?: "ok" | "danger" | "neutral";
}

export interface StatTileProps {
  label: string;
  value: string | number;
  sublabel?: string;
  delta?: StatTileDelta;
  className?: string;
}

const ARROW: Record<DeltaDirection, string> = { up: "▲", down: "▼", flat: "→" };

function deltaTone(delta: StatTileDelta): "ok" | "danger" | "neutral" {
  if (delta.tone) return delta.tone;
  if (delta.direction === "up") return "ok";
  if (delta.direction === "down") return "danger";
  return "neutral";
}

export function StatTile({ label, value, sublabel, delta, className }: StatTileProps) {
  return (
    <div className={cn("rounded-lg border border-hairline bg-surface-2 px-5 py-4", className)}>
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-2 flex items-baseline gap-2.5">
        <span className="font-mono text-3xl font-semibold tracking-tight text-primary">{value}</span>
        {delta && (
          <span className={cn("inline-flex items-center gap-1 font-mono text-sm", TONE[deltaTone(delta)].text)}>
            <span aria-hidden>{ARROW[delta.direction]}</span>
            {delta.value}
          </span>
        )}
      </div>
      {sublabel && <div className="mt-1.5 text-sm text-secondary">{sublabel}</div>}
    </div>
  );
}
