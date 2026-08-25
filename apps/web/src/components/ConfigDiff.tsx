import { DiffView } from "./DiffView";
import { sentenceDiff } from "../lib/diff";

export interface ToolEdit {
  tool_name: string;
  before: string;
  after: string;
}

export interface ConfigDiffProps {
  systemPromptBefore: string;
  systemPromptAfter: string;
  toolEdits: ToolEdit[];
  /** labels for the diff headers, e.g. "v1 → v2-p6-b" */
  fromLabel?: string;
  toLabel?: string;
}

/** How much of the configuration a patch actually touches, in one line. */
export function diffSummary({ systemPromptBefore, systemPromptAfter, toolEdits }: ConfigDiffProps): string {
  const { stats } = sentenceDiff(systemPromptBefore, systemPromptAfter);
  const changed = toolEdits.filter((e) => e.before !== e.after);
  const prompt =
    stats.added || stats.removed
      ? `${stats.removed} sentence${stats.removed === 1 ? "" : "s"} removed, ${stats.added} added`
      : "system prompt unchanged";
  return `${prompt} · ${changed.length} tool description${changed.length === 1 ? "" : "s"} rewritten`;
}

/**
 * The whole of a configuration change, as diffs.
 *
 * Shared by the patch candidates and the agent's configuration card so the
 * thing that was reviewed and the thing that shipped are rendered identically.
 */
export function ConfigDiff(props: ConfigDiffProps) {
  const { systemPromptBefore, systemPromptAfter, toolEdits, fromLabel, toLabel } = props;
  const header = fromLabel && toLabel ? `${fromLabel} → ${toLabel}` : "";
  const prompt = sentenceDiff(systemPromptBefore, systemPromptAfter);

  return (
    <div className="space-y-4">
      <DiffView
        diff={prompt.diff || " no change"}
        filename={header ? `system_prompt   ${header}` : "system_prompt"}
        showLineNumbers={false}
      />
      {toolEdits
        .filter((e) => e.before !== e.after)
        .map((e) => (
          <DiffView
            key={e.tool_name}
            diff={sentenceDiff(e.before, e.after).diff}
            filename={`tools.${e.tool_name}.description`}
            showLineNumbers={false}
          />
        ))}
    </div>
  );
}

export default ConfigDiff;
