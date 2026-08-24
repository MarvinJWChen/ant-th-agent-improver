import { cn } from "../lib/utils";

export interface CodeBlockProps {
  code: string;
  /** shown in a header bar above the code, e.g. a file path */
  filename?: string;
  /** short language/type tag shown next to the filename, e.g. "json" */
  language?: string;
  className?: string;
  /** cap the block's height and scroll vertically inside it */
  maxHeightClassName?: string;
}

export function CodeBlock({ code, filename, language, className, maxHeightClassName }: CodeBlockProps) {
  const hasHeader = !!filename || !!language;
  return (
    <div className={cn("overflow-hidden rounded-md border border-hairline bg-surface-2", className)}>
      {hasHeader && (
        <div className="flex items-center justify-between gap-2 border-b border-hairline px-3 py-1.5">
          {filename && <span className="truncate font-mono text-xs text-secondary">{filename}</span>}
          {language && (
            <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-muted">
              {language}
            </span>
          )}
        </div>
      )}
      <pre
        className={cn(
          "scrollbar-thin overflow-x-auto p-3 font-mono text-xs leading-relaxed text-primary",
          maxHeightClassName && cn("overflow-y-auto", maxHeightClassName),
        )}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}
