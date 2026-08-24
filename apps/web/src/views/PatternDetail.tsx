import { useParams } from "react-router-dom";
import { SectionHeading, EmptyState } from "../components";

/**
 * Placeholder — the lead engineer replaces this with the real "Diagnose"
 * view (LLM diagnosis of the pattern at :patternId, proposed config patch).
 */
export function PatternDetail() {
  const { patternId } = useParams<{ patternId: string }>();
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SectionHeading
        title="Diagnose"
        subtitle={`Route: /patterns/${patternId ?? ":patternId"} — placeholder view`}
      />
      <div className="mt-4">
        <EmptyState
          title="Pattern detail view not yet implemented"
          description={`This is a shell placeholder for step 3 of the journey (pattern "${patternId ?? "unknown"}"). The lead engineer wires this up to the LLM diagnosis and generated config patch.`}
        />
      </div>
    </div>
  );
}

export default PatternDetail;
