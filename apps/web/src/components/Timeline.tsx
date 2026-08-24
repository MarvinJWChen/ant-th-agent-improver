import { useState } from "react";
import { cn } from "../lib/utils";
import { TONE, type Tone } from "../lib/tone";
import { Badge } from "./Badge";

export type TimelineEventType =
  | "user_msg"
  | "model_turn"
  | "tool_call"
  | "tool_result"
  | "agent_msg"
  | "escalation"
  | (string & {});

export interface TimelineItem {
  id: string;
  seq: number;
  type: TimelineEventType;
  title: string;
  /** monospace payload block (e.g. JSON args/result), rendered collapsible */
  payload?: string;
  /** payload starts expanded (default collapsed) */
  payloadExpanded?: boolean;
  latencyMs?: number;
  error?: string;
  /** render with an accent rail — the event under discussion */
  highlight?: boolean;
  /** de-emphasize — e.g. events outside the matched pattern */
  dim?: boolean;
}

export interface TimelineProps {
  items: TimelineItem[];
  className?: string;
}

const TYPE_META: Record<string, { label: string; glyph: string; tone: Tone }> = {
  user_msg: { label: "User", glyph: "U", tone: "info" },
  model_turn: { label: "Model", glyph: "M", tone: "accent" },
  tool_call: { label: "Tool call", glyph: "→", tone: "neutral" },
  tool_result: { label: "Tool result", glyph: "←", tone: "neutral" },
  agent_msg: { label: "Agent", glyph: "A", tone: "ok" },
  escalation: { label: "Escalation", glyph: "!", tone: "danger" },
};

function typeMeta(type: string) {
  return TYPE_META[type] ?? { label: type, glyph: "•", tone: "neutral" as Tone };
}

function PayloadDisclosure({ id, payload, defaultExpanded }: { id: string; payload: string; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const domId = `timeline-payload-${id}`;
  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={domId}
        onClick={() => setExpanded((e) => !e)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded border border-hairline bg-surface-1 px-2 py-1 text-xs font-medium text-secondary",
          "transition-colors duration-120 hover:border-hairline-strong hover:text-primary",
        )}
      >
        <span aria-hidden>{expanded ? "▴" : "▾"}</span>
        {expanded ? "Hide payload" : "Show payload"}
      </button>
      {expanded && (
        <pre
          id={domId}
          className="scrollbar-thin mt-2 overflow-x-auto rounded-md border border-hairline bg-surface-1 p-3 font-mono text-sm text-secondary"
        >
          <code>{payload}</code>
        </pre>
      )}
    </div>
  );
}

/** Vertical trace-event timeline: sequence, type, title, latency/error chips, collapsible payload. */
export function Timeline({ items, className }: TimelineProps) {
  return (
    <ol className={cn("flex flex-col", className)}>
      {items.map((item, i) => {
        const meta = typeMeta(item.type);
        const isLast = i === items.length - 1;
        return (
          <li
            key={item.id}
            className={cn(
              "relative flex gap-4 pl-1 pr-2",
              item.highlight && "-ml-3 rounded-md border-l-2 border-accent bg-accent/5 pl-4",
              item.dim && "opacity-45",
            )}
          >
            <div className="relative flex w-7 shrink-0 flex-col items-center">
              {i > 0 && <span className="absolute top-0 h-1/2 w-px bg-hairline" aria-hidden />}
              {!isLast && <span className="absolute bottom-0 h-1/2 w-px bg-hairline" aria-hidden />}
              <span
                className={cn(
                  "relative z-10 mt-1.5 flex h-6 w-6 items-center justify-center rounded-full border font-mono text-xs",
                  TONE[meta.tone].bg,
                  TONE[meta.tone].border,
                  TONE[meta.tone].text,
                )}
                aria-hidden
              >
                {meta.glyph}
              </span>
            </div>
            <div className="min-w-0 flex-1 pb-6">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-mono text-xs text-muted">#{item.seq}</span>
                <Badge tone={meta.tone} mono>
                  {meta.label}
                </Badge>
                <span className="truncate text-base text-primary">{item.title}</span>
                {item.latencyMs != null && (
                  <Badge tone={item.latencyMs >= 2000 ? "warn" : "neutral"} mono>
                    {item.latencyMs}ms
                  </Badge>
                )}
                {item.error && (
                  <Badge tone="danger" mono>
                    {item.error}
                  </Badge>
                )}
              </div>
              {item.payload && (
                <PayloadDisclosure id={item.id} payload={item.payload} defaultExpanded={!!item.payloadExpanded} />
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
