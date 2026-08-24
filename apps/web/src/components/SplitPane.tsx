import type { ReactNode } from "react";
import { cn } from "../lib/utils";

export interface SplitPaneProps {
  leftLabel: ReactNode;
  rightLabel: ReactNode;
  left: ReactNode;
  right: ReactNode;
  /** small meta slot next to each label, e.g. a version Badge */
  leftMeta?: ReactNode;
  rightMeta?: ReactNode;
  className?: string;
}

/** Labelled two-column comparison layout (baseline vs candidate); stacks below the `md` breakpoint. */
export function SplitPane({ leftLabel, rightLabel, left, right, leftMeta, rightMeta, className }: SplitPaneProps) {
  return (
    <div className={cn("grid grid-cols-1 gap-6 md:grid-cols-2", className)}>
      <div className="min-w-0">
        <div className="mb-2.5 flex items-center justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted">{leftLabel}</span>
          {leftMeta}
        </div>
        <div className="min-w-0">{left}</div>
      </div>
      <div className="min-w-0">
        <div className="mb-2.5 flex items-center justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted">{rightLabel}</span>
          {rightMeta}
        </div>
        <div className="min-w-0">{right}</div>
      </div>
    </div>
  );
}
