"""Render a Claude Code session transcript into a readable HTML page.

The raw transcript is JSONL under ~/.claude/projects/<slug>/<session-id>.jsonl.
It is faithful but unreadable: most records are tool results, and a single
session here runs to megabytes. This keeps every human turn and every assistant
reply verbatim, compacts tool calls to one line each, and marks the points where
the session went idle or was interrupted and resumed.

    uv run python -m scripts.render_transcript --list
    uv run python -m scripts.render_transcript <session-id> -o transcript.html

Nothing is redacted automatically. Run --scan first and read what it reports.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"

# A user record is a real typed turn unless it is one of these injections.
INJECTION_MARKERS = (
    "<system-reminder>",
    "[SYSTEM NOTIFICATION",
    "<task-notification>",
    "Caveat: The messages below were generated",
)

RESUME_MARKER = "Continue from where you left off"
IDLE_GAP_SECONDS = 240

SECRET_PATTERNS = {
    "anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "openai key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "aws key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def sessions() -> list[tuple[Path, int, str]]:
    out = []
    for d in sorted(PROJECTS.glob("*")):
        for f in sorted(d.glob("*.jsonl")):
            n = sum(1 for _ in f.open(errors="ignore"))
            out.append((f, n, d.name))
    return out


def parse_ts(record: dict) -> dt.datetime | None:
    ts = record.get("timestamp")
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def blocks(record: dict) -> list[dict]:
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def is_injection(text: str) -> bool:
    head = text.lstrip()[:400]
    return any(m in head for m in INJECTION_MARKERS)


def scan_for_secrets(path: Path) -> dict[str, int]:
    hits: dict[str, int] = {}
    raw = path.read_text(errors="ignore")
    for name, pattern in SECRET_PATTERNS.items():
        found = pattern.findall(raw)
        if found:
            hits[name] = len(found)
    return hits


def build(path: Path) -> list[dict]:
    """Collapse the JSONL into an ordered list of conversation events.

    Two shapes need care. Messages typed while the assistant was still working
    are stored as `queue-operation` records, not user records, and each appears
    twice — those are the mid-turn asides, and dropping them would hide half the
    conversation. And a skill's instructions arrive as a user-role message right
    after a `Skill` tool call; attributing those to the human would be a plain
    misrepresentation of who said what.
    """
    events: list[dict] = []
    prev_ts: dt.datetime | None = None
    pending_tools: list[str] = []
    seen_queued: set[str] = set()
    after_skill_call = False

    def flush_tools() -> None:
        if pending_tools:
            events.append({"kind": "tools", "names": list(pending_tools)})
            pending_tools.clear()

    for line in path.open(errors="ignore"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = rec.get("type")

        if kind == "queue-operation":
            text = (rec.get("content") or "").strip()
            key = text[:200]
            if text and key not in seen_queued:
                seen_queued.add(key)
                flush_tools()
                # Background task completions arrive through the same queue as
                # typed messages. They are events, not things the human said.
                kindly = "system" if is_injection(text) else "human"
                events.append({"kind": kindly, "text": text, "at": parse_ts(rec),
                               "midturn": kindly == "human"})
            continue

        if kind not in ("user", "assistant"):
            continue

        ts = parse_ts(rec)
        if ts and prev_ts and (ts - prev_ts).total_seconds() > IDLE_GAP_SECONDS:
            flush_tools()
            events.append(
                {"kind": "gap", "minutes": (ts - prev_ts).total_seconds() / 60, "at": ts}
            )
        if ts:
            prev_ts = ts

        if kind == "user":
            text = "\n".join(
                b.get("text", "") for b in blocks(rec) if b.get("type") == "text"
            ).strip()
            if not text:
                continue  # tool_result record — the assistant's tool line already covers it
            flush_tools()
            if RESUME_MARKER in text:
                events.append({"kind": "resume", "at": ts})
            elif after_skill_call:
                events.append({"kind": "skill", "text": text, "at": ts})
            elif is_injection(text):
                events.append({"kind": "system", "text": text, "at": ts})
            else:
                events.append({"kind": "human", "text": text, "at": ts})
        else:
            said = "\n".join(
                b.get("text", "") for b in blocks(rec) if b.get("type") == "text"
            ).strip()
            used = [b.get("name", "?") for b in blocks(rec) if b.get("type") == "tool_use"]
            if said:
                flush_tools()
                events.append({"kind": "claude", "text": said, "at": ts})
            pending_tools.extend(used)
            if used:
                after_skill_call = "Skill" in used

    flush_tools()
    return events


def md_to_html(text: str) -> str:
    """Just enough markdown for a transcript: code, headings, lists, emphasis."""
    out: list[str] = []
    in_code = False
    for raw in text.split("\n"):
        if raw.startswith("```"):
            out.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(raw))
            continue
        line = html.escape(raw)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", line)
        if re.match(r"^#{1,6} ", raw):
            level = min(len(raw) - len(raw.lstrip("#")), 6)
            out.append(f"<h{level+2}>{line.lstrip('# ')}</h{level+2}>")
        elif re.match(r"^\s*[-*] ", raw):
            out.append(f"<li>{re.sub(r'^\s*[-*] ', '', line)}</li>")
        elif re.match(r"^\s*\d+\. ", raw):
            out.append(f"<li>{re.sub(r'^\s*\d+\. ', '', line)}</li>")
        elif not raw.strip():
            out.append("")
        else:
            out.append(f"<p>{line}</p>")
    if in_code:
        out.append("</code></pre>")

    joined = "\n".join(out)
    joined = re.sub(r"(?:<li>.*?</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", joined, flags=re.S)
    return joined


def render(events: list[dict], meta: dict) -> str:
    parts: list[str] = []
    turn = 0
    for e in events:
        k = e["kind"]
        if k == "human":
            turn += 1
            stamp = f"{e['at']:%H:%M}" if e.get("at") else ""
            tag = " · sent mid-turn" if e.get("midturn") else ""
            parts.append(
                f'<article class="turn human"><header><span class="who">Jingwei</span>'
                f'<span class="meta">turn {turn} · {stamp}{tag}</span></header>'
                f'<div class="body">{md_to_html(e["text"])}</div></article>'
            )
        elif k == "claude":
            stamp = f"{e['at']:%H:%M}" if e.get("at") else ""
            parts.append(
                f'<article class="turn claude"><header><span class="who">Claude</span>'
                f'<span class="meta">{stamp}</span></header>'
                f'<div class="body">{md_to_html(e["text"])}</div></article>'
            )
        elif k == "tools":
            counts: dict[str, int] = {}
            for n in e["names"]:
                counts[n] = counts.get(n, 0) + 1
            chips = " ".join(
                f'<span class="chip">{html.escape(n)}{"" if c == 1 else f" ×{c}"}</span>'
                for n, c in counts.items()
            )
            parts.append(f'<div class="tools">{chips}</div>')
        elif k == "gap":
            parts.append(
                f'<div class="gap"><span>idle {e["minutes"]:.0f} min</span></div>'
            )
        elif k == "resume":
            parts.append(
                '<div class="resume"><strong>Session interrupted and resumed</strong>'
                "<span>The process exited with background work in flight; the transcript "
                "continues in the same session.</span></div>"
            )
        elif k == "skill":
            first = e["text"].strip().split("\n")[0][:110]
            parts.append(
                f'<div class="sys">skill instructions loaded — {html.escape(first)}…</div>'
            )
        elif k == "system":
            t = e["text"].strip()
            if "task-notification" in t or "task-id" in t:
                label = "background task finished"
            else:
                label = t.split("\n")[0][:110]
            parts.append(f'<div class="sys">{html.escape(label)}</div>')

    return TEMPLATE.replace("{{BODY}}", "\n".join(parts)).replace(
        "{{META}}",
        f"{meta['humans']} human turns · {meta['claudes']} replies · "
        f"{meta['tools']} tool calls · {meta['span']}",
    )


TEMPLATE = """<title>Building Agent Improver</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;500&display=swap">
<style>
:root{--ground:#F4F7F8;--surface:#FFF;--sunken:#EAF0F2;--ink:#0D1519;--body:#22333C;--muted:#5C6B75;--line:#CBD8DD;--line-soft:#DFE8EB;--accent:#1F6F8B;--accent-soft:#E2EEF2;--warn:#9C6100;--warn-soft:#F8EEDB}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0E1418;--surface:#151E24;--sunken:#111A1F;--ink:#EAF1F4;--body:#C2D2DA;--muted:#8CA1AC;--line:#2B3A43;--line-soft:#1E2A31;--accent:#5FB3CE;--accent-soft:#16303B;--warn:#E0A44A;--warn-soft:#2C2213}}
:root[data-theme="dark"]{--ground:#0E1418;--surface:#151E24;--sunken:#111A1F;--ink:#EAF1F4;--body:#C2D2DA;--muted:#8CA1AC;--line:#2B3A43;--line-soft:#1E2A31;--accent:#5FB3CE;--accent-soft:#16303B;--warn:#E0A44A;--warn-soft:#2C2213}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--body);font-family:"IBM Plex Serif",Georgia,serif;font-size:16px;line-height:1.62}
.wrap{max-width:820px;margin:0 auto;padding:3.5rem 1.25rem 6rem;display:flex;flex-direction:column;gap:1.25rem}
header.top{border-bottom:1px solid var(--line);padding-bottom:1.75rem;margin-bottom:1rem}
h1{font-family:"IBM Plex Sans",sans-serif;font-size:2rem;font-weight:600;letter-spacing:-.02em;color:var(--ink);margin:0 0 .5rem}
.sub{color:var(--muted);font-size:.9rem;font-family:"IBM Plex Sans",sans-serif}
.turn{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:1.15rem 1.35rem;overflow:hidden}
.turn.human{background:var(--accent-soft);border-color:var(--accent)}
.turn header{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;margin-bottom:.6rem;font-family:"IBM Plex Sans",sans-serif}
.who{font-weight:600;font-size:.8rem;letter-spacing:.05em;text-transform:uppercase;color:var(--accent)}
.turn.claude .who{color:var(--muted)}
.meta{font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:var(--muted)}
.body>*:first-child{margin-top:0}.body>*:last-child{margin-bottom:0}
.body p{margin:0 0 .7rem}
.body h2,.body h3,.body h4,.body h5{font-family:"IBM Plex Sans",sans-serif;color:var(--ink);font-size:1.02rem;font-weight:600;margin:1.1rem 0 .5rem}
.body ul{margin:.2rem 0 .8rem;padding-left:1.2rem}
.body li{margin-bottom:.3rem}
code{font-family:"IBM Plex Mono",monospace;font-size:.86em;background:var(--sunken);border:1px solid var(--line-soft);border-radius:3px;padding:.05em .3em}
pre{background:var(--sunken);border:1px solid var(--line-soft);border-radius:6px;padding:.8rem 1rem;overflow-x:auto;margin:.6rem 0}
pre code{background:none;border:none;padding:0;font-size:.8rem;line-height:1.5}
.tools{display:flex;flex-wrap:wrap;gap:.35rem;padding:0 .3rem}
.chip{font-family:"IBM Plex Mono",monospace;font-size:.7rem;color:var(--muted);background:var(--sunken);border:1px solid var(--line-soft);border-radius:3px;padding:.1rem .4rem}
.gap{display:flex;align-items:center;gap:.75rem;color:var(--muted);font-family:"IBM Plex Sans",sans-serif;font-size:.75rem;padding:.15rem .3rem}
.gap::before,.gap::after{content:"";flex:1;height:1px;background:var(--line-soft)}
.resume{background:var(--warn-soft);border:1px solid var(--warn);border-radius:8px;padding:.9rem 1.15rem;display:flex;flex-direction:column;gap:.25rem;font-family:"IBM Plex Sans",sans-serif;font-size:.85rem}
.resume strong{color:var(--ink)}.resume span{color:var(--muted)}
.sys{font-family:"IBM Plex Mono",monospace;font-size:.7rem;color:var(--muted);padding:.1rem .3rem;opacity:.75}
</style>
<div class="wrap">
<header class="top">
<h1>Building Agent Improver</h1>
<p class="sub">{{META}}</p>
</header>
{{BODY}}
</div>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session", nargs="?", help="session id (or a path to the .jsonl)")
    ap.add_argument("-o", "--out", default="transcript.html")
    ap.add_argument("--list", action="store_true", help="list available sessions")
    ap.add_argument("--scan", action="store_true", help="scan for secrets and exit")
    args = ap.parse_args()

    if args.list or not args.session:
        print(f"{'session':40s} {'lines':>7s}  project")
        for f, n, proj in sessions():
            print(f"{f.stem:40s} {n:7d}  {proj}")
        return 0

    path = Path(args.session)
    if not path.exists():
        matches = [f for f, _, _ in sessions() if f.stem == args.session]
        if not matches:
            print(f"no session {args.session!r}; try --list", file=sys.stderr)
            return 2
        path = matches[0]

    hits = scan_for_secrets(path)
    if hits:
        print("SECRETS FOUND — do not share this transcript as-is:", file=sys.stderr)
        for name, n in hits.items():
            print(f"  {name}: {n} occurrence(s)", file=sys.stderr)
        if args.scan:
            return 1
        print("  refusing to render; remove them first", file=sys.stderr)
        return 1
    print("secret scan: clean")
    if args.scan:
        return 0

    events = build(path)
    humans = sum(1 for e in events if e["kind"] == "human")
    claudes = sum(1 for e in events if e["kind"] == "claude")
    tools = sum(len(e["names"]) for e in events if e["kind"] == "tools")
    stamps = [e["at"] for e in events if e.get("at")]
    span = (
        f"{min(stamps):%d %b %H:%M} → {max(stamps):%H:%M} UTC" if stamps else "unknown span"
    )

    out = Path(args.out)
    out.write_text(
        render(events, {"humans": humans, "claudes": claudes, "tools": tools, "span": span})
    )
    print(
        f"wrote {out} — {humans} human turns, {claudes} replies, {tools} tool calls, "
        f"{out.stat().st_size / 1024:.0f} KB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
