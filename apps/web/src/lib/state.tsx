import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { JourneyStepId, JourneyStepStatus } from "./journey";

/**
 * Journey progress. Steps unlock as the audience completes them, so the stepper
 * reflects what has actually been done rather than just where the URL points.
 */
export interface JourneyState {
  discovered: boolean;
  diagnosed: string[];
  patched: string[];
  replayed: string[];
  promotedVersion: string | null;
  activePatternId?: string;
}

const EMPTY: JourneyState = {
  discovered: false,
  diagnosed: [],
  patched: [],
  replayed: [],
  promotedVersion: null,
};

const KEY = "agent-improver-journey";

interface Ctx extends JourneyState {
  mark: (patch: Partial<JourneyState>) => void;
  add: (key: "diagnosed" | "patched" | "replayed", value: string) => void;
  stepStatuses: Partial<Record<JourneyStepId, JourneyStepStatus>>;
  reset: () => void;
}

const JourneyCtx = createContext<Ctx | null>(null);

function load(): JourneyState {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function JourneyProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<JourneyState>(load);

  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* private mode — progress just won't survive a reload */
    }
  }, [state]);

  const mark = useCallback((patch: Partial<JourneyState>) => {
    setState((s) => ({ ...s, ...patch }));
  }, []);

  const add = useCallback((key: "diagnosed" | "patched" | "replayed", value: string) => {
    setState((s) => (s[key].includes(value) ? s : { ...s, [key]: [...s[key], value] }));
  }, []);

  const reset = useCallback(() => setState(EMPTY), []);

  const stepStatuses = useMemo(() => {
    const out: Partial<Record<JourneyStepId, JourneyStepStatus>> = {};
    if (!state.discovered) {
      out.diagnose = "locked";
      out.replay = "locked";
      out.proposals = "locked";
    } else if (state.diagnosed.length === 0) {
      out.replay = "locked";
    } else if (state.patched.length === 0) {
      out.replay = "locked";
    }
    return out;
  }, [state]);

  const value = useMemo(
    () => ({ ...state, mark, add, stepStatuses, reset }),
    [state, mark, add, stepStatuses, reset],
  );
  return <JourneyCtx.Provider value={value}>{children}</JourneyCtx.Provider>;
}

export function useJourney(): Ctx {
  const ctx = useContext(JourneyCtx);
  if (!ctx) throw new Error("useJourney must be used inside JourneyProvider");
  return ctx;
}

/** Minimal async helper: run on mount, expose {data, error, loading, reload}. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1) };
}

/** An action the audience triggers: tracks in-flight state and the last error. */
export function useAction<T>() {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const run = useCallback(async (tag: string, fn: () => Promise<T>) => {
    setPending(tag);
    setError(null);
    try {
      const d = await fn();
      setData(d);
      return d;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setPending(null);
    }
  }, []);

  return { data, setData, error, pending, run };
}
