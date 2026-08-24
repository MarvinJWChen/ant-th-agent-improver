import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { cn } from "../lib/utils";
import {
  JOURNEY_STEPS,
  derivePatternIdFromPath,
  findStepByPath,
  type JourneyStepId,
  type JourneyStepStatus,
} from "../lib/journey";
import { JourneyStepper } from "./JourneyStepper";

export interface ShellProps {
  children?: ReactNode;
  /** product name in the top bar; defaults to "Agent Improver" */
  productName?: string;
  /** the monitored agent's name/slug, shown next to the product name */
  agentName?: string;
  /** slot on the right of the top bar for the lead to fill (env indicator, user menu, ...) */
  rightSlot?: ReactNode;
  /**
   * Currently active journey step. When omitted, it's derived from the
   * current route via each step's `matches(pathname)`.
   */
  currentStepId?: JourneyStepId;
  /** override individual step statuses, e.g. lock Proposals until the gate passes */
  stepStatuses?: Partial<Record<JourneyStepId, JourneyStepStatus>>;
  /**
   * Pattern id used to resolve the Diagnose (/patterns/:id) and Replay
   * (/replay/:id) stepper links. When omitted, it's parsed from the
   * current route if present.
   */
  activePatternId?: string;
  className?: string;
}

/**
 * Fixed top bar + journey stepper + content area. Wrap the router's <Routes>
 * with this once, near the top of the tree (see src/App.tsx).
 */
export function Shell({
  children,
  productName = "Agent Improver",
  agentName,
  rightSlot,
  currentStepId,
  stepStatuses,
  activePatternId,
  className,
}: ShellProps) {
  const location = useLocation();
  const resolvedStepId = currentStepId ?? findStepByPath(location.pathname)?.id ?? JOURNEY_STEPS[0].id;
  const resolvedPatternId = activePatternId ?? derivePatternIdFromPath(location.pathname);

  return (
    <div className={cn("flex min-h-screen flex-col bg-surface-0", className)}>
      <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-hairline bg-surface-1 px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-base font-semibold tracking-tight text-primary">{productName}</span>
          {agentName && (
            <>
              <span className="text-hairline-strong" aria-hidden>
                /
              </span>
              <span className="truncate font-mono text-sm text-secondary">{agentName}</span>
            </>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">{rightSlot}</div>
      </header>

      <JourneyStepper
        currentStepId={resolvedStepId}
        statuses={stepStatuses}
        activePatternId={resolvedPatternId}
        className="sticky top-16 z-10"
      />

      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
