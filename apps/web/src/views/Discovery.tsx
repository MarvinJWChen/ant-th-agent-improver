import { SectionHeading, EmptyState } from "../components";

/**
 * Placeholder — the lead engineer replaces this with the real Discovery view
 * (clustered failure patterns table, links into /patterns/:patternId).
 */
export function Discovery() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SectionHeading title="Discovery" subtitle="Route: /discovery — placeholder view" />
      <div className="mt-4">
        <EmptyState
          title="Discovery view not yet implemented"
          description="This is a shell placeholder for step 2 of the journey. The lead engineer wires this up to discovered failure-pattern clusters."
        />
      </div>
    </div>
  );
}

export default Discovery;
