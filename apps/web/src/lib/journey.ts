/**
 * The 5-step improvement journey that drives the top-of-app stepper.
 * Overview -> Discovery -> Diagnose -> Replay & Gate -> Proposals
 *
 * This module is the single source of truth for step order, labels, and
 * routing so views and the Shell/JourneyStepper stay in sync. The lead
 * engineer drives *state* (which step is current/locked) via props on
 * <Shell> / <JourneyStepper> — this file only defines the static shape.
 */

export type JourneyStepId =
  | "overview"
  | "discovery"
  | "diagnose"
  | "replay"
  | "proposals";

export type JourneyStepStatus = "completed" | "current" | "upcoming" | "locked";

export interface JourneyStepDef {
  /** stable identifier */
  id: JourneyStepId;
  /** 1-based position in the journey */
  index: number;
  /** label shown in the stepper */
  label: string;
  /**
   * Route to navigate to when this step is clicked. Steps 3 and 4
   * (diagnose/replay) are parameterized by the pattern under investigation;
   * pass the currently active pattern id via `resolveStepPath` /
   * <JourneyStepper activePatternId>. Falls back to Discovery when no
   * pattern id is available yet.
   */
  path: string | ((patternId?: string) => string);
  /** does this pathname belong to this step? used to auto-derive "current" */
  matches: (pathname: string) => boolean;
}

export const JOURNEY_STEPS: JourneyStepDef[] = [
  {
    id: "overview",
    index: 1,
    label: "Overview",
    path: "/",
    matches: (p) => p === "/",
  },
  {
    id: "discovery",
    index: 2,
    label: "Discovery",
    path: "/discovery",
    matches: (p) => p === "/discovery",
  },
  {
    id: "diagnose",
    index: 3,
    label: "Diagnose",
    path: (patternId) => (patternId ? `/patterns/${patternId}` : "/discovery"),
    matches: (p) => p.startsWith("/patterns/"),
  },
  {
    id: "replay",
    index: 4,
    label: "Replay & Gate",
    path: (patternId) => (patternId ? `/replay/${patternId}` : "/discovery"),
    matches: (p) => p.startsWith("/replay/"),
  },
  {
    id: "proposals",
    index: 5,
    label: "Proposals",
    path: "/proposals",
    matches: (p) => p === "/proposals",
  },
];

export function resolveStepPath(step: JourneyStepDef, patternId?: string): string {
  return typeof step.path === "function" ? step.path(patternId) : step.path;
}

/** Find the journey step whose route matches the given pathname, if any. */
export function findStepByPath(pathname: string): JourneyStepDef | undefined {
  return JOURNEY_STEPS.find((step) => step.matches(pathname));
}

/**
 * Default status for a step given the current step's index — used when the
 * caller doesn't explicitly override a step's status. Steps before the
 * current one are "completed", the current one is "current", everything
 * after is "upcoming". Nothing is ever defaulted to "locked" — that's an
 * explicit, data-driven decision the lead makes via `stepStatuses`.
 */
export function defaultStepStatus(
  step: JourneyStepDef,
  currentIndex: number,
): JourneyStepStatus {
  if (step.index < currentIndex) return "completed";
  if (step.index === currentIndex) return "current";
  return "upcoming";
}

/** Extract a `:patternId`-shaped segment from /patterns/:id or /replay/:id. */
export function derivePatternIdFromPath(pathname: string): string | undefined {
  const match = /^\/(?:patterns|replay)\/([^/]+)/.exec(pathname);
  return match?.[1];
}
