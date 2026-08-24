import { useParams } from "react-router-dom";
import { SectionHeading, EmptyState } from "../components";

/**
 * Placeholder — the lead engineer replaces this with the real "Replay & Gate"
 * view (frozen-world replay of the candidate patch for :patternId, gate checklist).
 */
export function Replay() {
  const { patternId } = useParams<{ patternId: string }>();
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SectionHeading
        title="Replay & Gate"
        subtitle={`Route: /replay/${patternId ?? ":patternId"} — placeholder view`}
      />
      <div className="mt-4">
        <EmptyState
          title="Replay view not yet implemented"
          description={`This is a shell placeholder for step 4 of the journey (pattern "${patternId ?? "unknown"}"). The lead engineer wires this up to replay results and the promotion gate.`}
        />
      </div>
    </div>
  );
}

export default Replay;
