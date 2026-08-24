import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./components";
import { Overview } from "./views/Overview";
import { Discovery } from "./views/Discovery";
import { PatternDetail } from "./views/PatternDetail";
import { Replay } from "./views/Replay";
import { Proposals } from "./views/Proposals";
import { Kit } from "./views/Kit";
import { JourneyProvider, useJourney } from "./lib/state";
import { derivePatternIdFromPath } from "./lib/journey";

function NotFound() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <p className="text-sm text-muted">Route not found.</p>
    </div>
  );
}

function Inner() {
  const journey = useJourney();
  const loc = useLocation();
  const patternId = derivePatternIdFromPath(loc.pathname) ?? journey.activePatternId;

  return (
    <Shell
      agentName="support-refund-agent"
      activePatternId={patternId}
      stepStatuses={journey.stepStatuses}
      rightSlot={
        <span className="font-mono text-[11px] text-muted">
          {journey.promotedVersion ? `active: ${journey.promotedVersion}` : "active: v1"}
        </span>
      }
    >
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/discovery" element={<Discovery />} />
        <Route path="/patterns/:patternId" element={<PatternDetail />} />
        <Route path="/replay/:patternId" element={<Replay />} />
        <Route path="/proposals" element={<Proposals />} />
        <Route path="/kit" element={<Kit />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Shell>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <JourneyProvider>
        <Inner />
      </JourneyProvider>
    </BrowserRouter>
  );
}
