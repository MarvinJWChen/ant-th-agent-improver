import type { ReactNode } from "react";
import { cn } from "../lib/utils";
import { TONE, type Tone } from "../lib/tone";

export type BadgeTone = Tone;

export interface BadgeProps {
  tone?: BadgeTone;
  /** leading solid dot indicator */
  dot?: boolean;
  /** use monospace type (identifiers, counts, hashes) */
  mono?: boolean;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", dot = false, mono = false, className, children }: BadgeProps) {
  const t = TONE[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs leading-none",
        t.bg,
        t.border,
        t.text,
        mono && "font-mono",
        className,
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", t.dot)} />}
      {children}
    </span>
  );
}
