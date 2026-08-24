import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components";
import { Overview } from "./views/Overview";
import { Discovery } from "./views/Discovery";
import { PatternDetail } from "./views/PatternDetail";
import { Replay } from "./views/Replay";
import { Proposals } from "./views/Proposals";
import { Kit } from "./views/Kit";

function NotFound() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <p className="text-sm text-muted">Route not found.</p>
    </div>
  );
}

/**
 * App root: router + shell (top bar + journey stepper) + routed views.
 * Views are placeholders — the lead engineer replaces their contents and
 * owns all data fetching. See src/lib/journey.ts for the step definitions
 * and src/components/Shell.tsx for the props that drive stepper state
 * (currentStepId, stepStatuses, activePatternId, rightSlot).
 */
export default function App() {
  return (
    <BrowserRouter>
      <Shell
        agentName="refund-agent"
        rightSlot={<span className="text-xs text-muted">right slot — lead fills this in</span>}
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
    </BrowserRouter>
  );
}
