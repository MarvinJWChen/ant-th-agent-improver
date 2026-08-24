import { SectionHeading, EmptyState } from "../components";

/**
 * Placeholder — the lead engineer replaces this with the real Proposals view
 * (versioned config patches, promotion status, provenance).
 */
export function Proposals() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SectionHeading title="Proposals" subtitle="Route: /proposals — placeholder view" />
      <div className="mt-4">
        <EmptyState
          title="Proposals view not yet implemented"
          description="This is a shell placeholder for step 5 of the journey. The lead engineer wires this up to promoted/candidate config versions."
        />
      </div>
    </div>
  );
}

export default Proposals;
