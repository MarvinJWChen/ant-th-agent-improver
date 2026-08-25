/**
 * Sentence-level diffing for configuration text.
 *
 * The agent's system prompt is one long unbroken line, so a line diff renders
 * as "everything removed, everything added" and shows nothing. Splitting on
 * sentence boundaries first makes the actual edit visible: the surgical
 * candidate reads as one clause removed against unchanged context.
 */

/** Split text into diffable segments: blank lines kept, sentences separated. */
export function segments(text: string): string[] {
  const out: string[] = [];
  for (const para of text.split("\n")) {
    if (!para.trim()) continue; // blank lines would diff as empty +/- rows
    // Break after . : ; ? ! — but not after an enumerator, so "1." stays attached.
    for (const s of para.split(/(?<![0-9]\.)(?<=[.:;?!])\s+/)) {
      if (s.trim()) out.push(s.trim());
    }
  }
  return out;
}

/** Longest common subsequence table, small inputs only (prompts are ~30 segments). */
function lcs(a: string[], b: string[]): number[][] {
  const t: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      t[i][j] = a[i] === b[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
    }
  }
  return t;
}

export interface DiffStats {
  added: number;
  removed: number;
  unchanged: number;
}

/**
 * A unified diff over sentence segments, in the format `DiffView` already parses.
 * Unchanged runs longer than `context` collapse to a hunk marker.
 */
export function sentenceDiff(before: string, after: string, context = 1): { diff: string; stats: DiffStats } {
  const a = segments(before);
  const b = segments(after);
  const t = lcs(a, b);

  const rows: { sign: " " | "+" | "-"; text: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      rows.push({ sign: " ", text: a[i] });
      i++;
      j++;
    } else if (t[i + 1][j] >= t[i][j + 1]) {
      rows.push({ sign: "-", text: a[i++] });
    } else {
      rows.push({ sign: "+", text: b[j++] });
    }
  }
  while (i < a.length) rows.push({ sign: "-", text: a[i++] });
  while (j < b.length) rows.push({ sign: "+", text: b[j++] });

  const stats: DiffStats = {
    added: rows.filter((r) => r.sign === "+" && r.text).length,
    removed: rows.filter((r) => r.sign === "-" && r.text).length,
    unchanged: rows.filter((r) => r.sign === " ").length,
  };

  // Keep `context` unchanged rows either side of a change; elide the rest.
  const keep = rows.map((r) => r.sign !== " ");
  rows.forEach((r, k) => {
    if (r.sign === " ") return;
    for (let d = -context; d <= context; d++) if (rows[k + d]) keep[k + d] = true;
  });

  const lines: string[] = [];
  let elided = false;
  rows.forEach((r, k) => {
    if (!keep[k]) {
      elided = true;
      return;
    }
    if (elided) {
      lines.push("@@ unchanged text @@");
      elided = false;
    }
    lines.push(r.sign + r.text);
  });

  return { diff: lines.join("\n"), stats };
}
