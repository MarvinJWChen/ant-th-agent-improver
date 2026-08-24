import { Fragment } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "../lib/utils";
import {
  JOURNEY_STEPS,
  defaultStepStatus,
  resolveStepPath,
  type JourneyStepId,
  type JourneyStepStatus,
} from "../lib/journey";

export interface JourneyStepperProps {
  currentStepId: JourneyStepId;
  /** override individual step statuses, e.g. to lock Proposals until the gate passes */
  statuses?: Partial<Record<JourneyStepId, JourneyStepStatus>>;
  /** pattern id used to resolve the Diagnose/Replay step links */
  activePatternId?: string;
  className?: string;
}

const CIRCLE_BASE = "flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[11px]";

const CIRCLE_STATUS: Record<JourneyStepStatus, string> = {
  completed: "bg-ok/10 text-ok border border-ok/30",
  current: "bg-accent text-surface-0 border border-accent",
  upcoming: "bg-surface-2 text-muted border border-hairline-strong",
  locked: "bg-surface-2 text-muted/60 border border-hairline",
};

const STEP_BUTTON_STATUS: Record<JourneyStepStatus, string> = {
  completed: "text-secondary hover:text-primary hover:bg-surface-2",
  current: "text-primary bg-surface-2/70 shadow-[inset_0_-2px_0_0_rgb(var(--color-accent))]",
  upcoming: "text-muted",
  locked: "text-muted/60",
};

/**
 * The 5-step journey spine: Overview -> Discovery -> Diagnose -> Replay & Gate -> Proposals.
 * Clicking a "completed" or "current" step navigates; "upcoming"/"locked" steps render
 * as disabled (non-focusable) buttons.
 */
export function JourneyStepper({ currentStepId, statuses, activePatternId, className }: JourneyStepperProps) {
  const navigate = useNavigate();
  const currentIndex = JOURNEY_STEPS.find((s) => s.id === currentStepId)?.index ?? 1;

  function statusOf(stepId: JourneyStepId): JourneyStepStatus {
    const step = JOURNEY_STEPS.find((s) => s.id === stepId)!;
    return statuses?.[stepId] ?? defaultStepStatus(step, currentIndex);
  }

  return (
    <nav aria-label="Improvement journey" className={cn("border-b border-hairline bg-surface-1", className)}>
      <ol className="scrollbar-thin flex items-center overflow-x-auto px-4">
        {JOURNEY_STEPS.map((step, i) => {
          const status = statusOf(step.id);
          const clickable = status === "completed" || status === "current";
          const prevCompleted = i > 0 && statusOf(JOURNEY_STEPS[i - 1].id) === "completed";
          const path = resolveStepPath(step, activePatternId);

          return (
            <Fragment key={step.id}>
              {i > 0 && (
                <li aria-hidden className="mx-1 h-px min-w-[16px] flex-1">
                  <div className={cn("h-px w-full", prevCompleted ? "bg-ok/40" : "bg-hairline")} />
                </li>
              )}
              <li className="shrink-0">
                <button
                  type="button"
                  disabled={!clickable}
                  aria-current={status === "current" ? "step" : undefined}
                  onClick={() => clickable && navigate(path)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium",
                    "transition-colors duration-120 disabled:cursor-not-allowed",
                    clickable && "cursor-pointer",
                    STEP_BUTTON_STATUS[status],
                  )}
                >
                  <span className={cn(CIRCLE_BASE, CIRCLE_STATUS[status])} aria-hidden>
                    {status === "completed" ? "✓" : step.index}
                  </span>
                  <span className="whitespace-nowrap">{step.label}</span>
                  {status === "locked" && (
                    <span className="text-muted/60" aria-hidden>
                      🔒
                    </span>
                  )}
                </button>
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
