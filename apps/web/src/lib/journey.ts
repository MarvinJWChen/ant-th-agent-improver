/**
 * The improvement journey that drives the top-of-app stepper.
 *
 *   Agents → Agent → Discover → Investigate → Improve
 *
 * Step 5 is deliberately a single destination per pattern. A pattern is either
 * fixable by configuration — in which case Improve is replay, gate and promote —
 * or it is not, in which case Improve is a written proposal. Splitting those
 * into separate top-level views left people unable to find the replay step, and
 * showed every pattern's remediation on one page.
 */

export type JourneyStepId =
  | "agents"
  | "overview"
  | "discovery"
  | "investigate"
  | "improve";

export type JourneyStepStatus = "completed" | "current" | "upcoming" | "locked";

export interface JourneyStepDef {
  id: JourneyStepId;
  /** 1-based position in the journey */
  index: number;
  /** label shown in the stepper */
  label: string;
  /** one-line hint shown under the label on wider screens */
  hint: string;
  /** route to navigate to; steps 4 and 5 need the pattern under investigation */
  path: string | ((patternId?: string) => string);
  matches: (pathname: string) => boolean;
}

export const DEFAULT_AGENT_ID = "support-refund-agent";

export const JOURNEY_STEPS: JourneyStepDef[] = [
  {
    id: "agents",
    index: 1,
    label: "Agents",
    hint: "pick a managed agent",
    path: "/",
    matches: (p) => p === "/",
  },
  {
    id: "overview",
    index: 2,
    label: "Agent",
    hint: "traces and configuration",
    path: `/agents/${DEFAULT_AGENT_ID}`,
    matches: (p) => p.startsWith("/agents/"),
  },
  {
    id: "discovery",
    index: 3,
    label: "Discover",
    hint: "recurring patterns",
    path: "/discovery",
    matches: (p) => p === "/discovery",
  },
  {
    id: "investigate",
    index: 4,
    label: "Investigate",
    hint: "evidence and diagnosis",
    path: (patternId) => (patternId ? `/patterns/${patternId}` : "/discovery"),
    matches: (p) => /^\/patterns\/[^/]+$/.test(p),
  },
  {
    id: "improve",
    index: 5,
    label: "Improve",
    hint: "evaluate and promote",
    path: (patternId) => (patternId ? `/patterns/${patternId}/improve` : "/discovery"),
    matches: (p) => /^\/patterns\/[^/]+\/improve$/.test(p),
  },
];

export function resolveStepPath(step: JourneyStepDef, patternId?: string): string {
  return typeof step.path === "function" ? step.path(patternId) : step.path;
}

export function findStepByPath(pathname: string): JourneyStepDef | undefined {
  return JOURNEY_STEPS.find((step) => step.matches(pathname));
}

export function defaultStepStatus(
  step: JourneyStepDef,
  currentIndex: number,
): JourneyStepStatus {
  if (step.index < currentIndex) return "completed";
  if (step.index === currentIndex) return "current";
  return "upcoming";
}

/** Extract the `:patternId` segment from /patterns/:id or /patterns/:id/improve. */
export function derivePatternIdFromPath(pathname: string): string | undefined {
  return /^\/patterns\/([^/]+)/.exec(pathname)?.[1];
}
