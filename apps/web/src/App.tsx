import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ResetDemo, Shell } from "./components";
import { Agents } from "./views/Agents";
import { Overview } from "./views/Overview";
import { Discovery } from "./views/Discovery";
import { Investigate } from "./views/Investigate";
import { Improve } from "./views/Improve";
import { Kit } from "./views/Kit";
import { JourneyProvider, useJourney } from "./lib/state";
import { DEFAULT_AGENT_ID, derivePatternIdFromPath } from "./lib/journey";

function NotFound() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-16">
      <p className="text-muted">Route not found.</p>
    </div>
  );
}

function Inner() {
  const journey = useJourney();
  const loc = useLocation();
  const patternId = derivePatternIdFromPath(loc.pathname) ?? journey.activePatternId;
  const onLanding = loc.pathname === "/";

  return (
    <Shell
      agentName={onLanding ? undefined : DEFAULT_AGENT_ID}
      activePatternId={patternId}
      stepStatuses={journey.stepStatuses}
      rightSlot={<ResetDemo activeVersion={journey.promotedVersion ?? "v1"} />}
    >
      <Routes>
        <Route path="/" element={<Agents />} />
        <Route path="/agents/:agentId" element={<Overview />} />
        <Route path="/discovery" element={<Discovery />} />
        <Route path="/patterns/:patternId" element={<Investigate />} />
        <Route path="/patterns/:patternId/improve" element={<Improve />} />
        {/* old routes, kept so a stale tab or bookmark still lands somewhere sane */}
        <Route path="/replay/:patternId" element={<RedirectToImprove />} />
        <Route path="/proposals" element={<Navigate to="/discovery" replace />} />
        <Route path="/kit" element={<Kit />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Shell>
  );
}

function RedirectToImprove() {
  const loc = useLocation();
  const id = derivePatternIdFromPath(loc.pathname.replace("/replay/", "/patterns/"));
  return <Navigate to={id ? `/patterns/${id}/improve` : "/discovery"} replace />;
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
