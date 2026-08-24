import { useEffect, useState } from "react";
import { Button } from "./Button";

/**
 * Returns the deployment to what a fresh visitor sees.
 *
 * A rehearsal ends with a promoted configuration, so without this the only way
 * back to the baseline is a redeploy. Destructive enough to confirm first, and
 * it reloads afterwards so every view refetches rather than showing stale state
 * from before the reset.
 */
export function ResetDemo({ activeVersion }: { activeVersion: string }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 6000);
    return () => clearTimeout(t);
  }, [armed]);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/demo/reset", { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
      try {
        sessionStorage.removeItem("agent-improver-journey");
      } catch {
        /* private mode — the reload still lands on a clean journey */
      }
      window.location.assign("/");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
      setArmed(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-muted">active: {activeVersion}</span>
      <Button
        size="sm"
        variant={armed ? "danger" : "ghost"}
        loading={busy}
        onClick={() => (armed ? run() : setArmed(true))}
        title="Restore the baseline configuration and clear generated candidates, replay runs and world clones."
      >
        {busy ? "Resetting…" : armed ? "Confirm reset" : "Reset demo"}
      </Button>
      {error && <span className="text-danger">{error}</span>}
    </div>
  );
}

export default ResetDemo;
