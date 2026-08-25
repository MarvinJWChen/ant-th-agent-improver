import { useMemo } from "react";
import { cn } from "../lib/utils";

type DiffLineKind = "add" | "remove" | "context" | "hunk" | "meta";

interface ParsedDiffLine {
  kind: DiffLineKind;
  content: string;
  oldLine?: number;
  newLine?: number;
}

const HUNK_RE = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;

function parseDiff(diff: string): ParsedDiffLine[] {
  const rawLines = diff.split("\n");
  // drop a single trailing empty line from a final "\n"
  if (rawLines.length > 0 && rawLines[rawLines.length - 1] === "") rawLines.pop();

  const result: ParsedDiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const raw of rawLines) {
    if (raw.startsWith("@@")) {
      const m = HUNK_RE.exec(raw);
      if (m) {
        oldLine = parseInt(m[1], 10);
        newLine = parseInt(m[3], 10);
      }
      result.push({ kind: "hunk", content: raw });
      continue;
    }
    if (raw.startsWith("+++") || raw.startsWith("---")) {
      result.push({ kind: "meta", content: raw });
      continue;
    }
    if (raw.startsWith("+")) {
      result.push({ kind: "add", content: raw.slice(1), newLine });
      newLine += 1;
      continue;
    }
    if (raw.startsWith("-")) {
      result.push({ kind: "remove", content: raw.slice(1), oldLine });
      oldLine += 1;
      continue;
    }
    const content = raw.startsWith(" ") ? raw.slice(1) : raw;
    result.push({ kind: "context", content, oldLine, newLine });
    oldLine += 1;
    newLine += 1;
  }

  return result;
}

const ROW_TONE: Record<DiffLineKind, string> = {
  add: "bg-ok/10",
  remove: "bg-danger/10",
  hunk: "bg-accent/10 text-accent",
  meta: "text-muted",
  context: "text-secondary",
};

const SIGN: Record<DiffLineKind, string> = {
  add: "+",
  remove: "-",
  hunk: "",
  meta: "",
  context: " ",
};

export interface DiffViewProps {
  /** raw unified diff text (+/-/@@/context lines) */
  diff: string;
  /** optional filename shown in a header bar above the diff */
  filename?: string;
  /** off for prose diffs, where a segment index is not a line number */
  showLineNumbers?: boolean;
  className?: string;
}

/** Unified-diff renderer: line numbers, add/remove backgrounds, its own horizontal scroll container. */
export function DiffView({ diff, filename, showLineNumbers = true, className }: DiffViewProps) {
  const lines = useMemo(() => parseDiff(diff), [diff]);

  return (
    <div className={cn("overflow-hidden rounded-lg border border-hairline bg-surface-2", className)}>
      {filename && (
        <div className="border-b border-hairline bg-surface-1 px-4 py-2.5 font-mono text-sm text-secondary">
          {filename}
        </div>
      )}
      <div className="scrollbar-thin overflow-x-auto">
        <table className={cn("w-full border-collapse font-mono text-sm", showLineNumbers && "min-w-max")}>
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className={ROW_TONE[line.kind]}>
                {showLineNumbers && (
                  <>
                    <td className="w-12 select-none whitespace-nowrap px-2 py-1 text-right text-muted/70">
                      {line.oldLine ?? ""}
                    </td>
                    <td className="w-12 select-none whitespace-nowrap px-2 py-1 text-right text-muted/70">
                      {line.newLine ?? ""}
                    </td>
                  </>
                )}
                <td className="w-5 select-none px-1 py-1 text-center text-muted/70">{SIGN[line.kind]}</td>
                <td
                  className={cn(
                    "px-2 py-1",
                    showLineNumbers ? "whitespace-pre" : "max-w-[60rem] whitespace-pre-wrap",
                  )}
                >
                  {line.content}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
