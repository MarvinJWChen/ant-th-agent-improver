import { SectionHeading, EmptyState } from "../components";

/**
 * Placeholder — the lead engineer replaces this with the real Overview view
 * (trace volume, outcome mix, entry point into Discovery).
 */
export function Overview() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SectionHeading title="Overview" subtitle="Route: / — placeholder view" />
      <div className="mt-4">
        <EmptyState
          title="Overview view not yet implemented"
          description="This is a shell placeholder for step 1 of the journey. The lead engineer wires this up to /api trace summary data."
        />
      </div>
    </div>
  );
}

export default Overview;
