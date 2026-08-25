# docs

`architecture.html` is the source of the published architecture diagram:

    https://claude.ai/code/artifact/238a97c1-6c2b-450e-a9d9-6018baa126f5

It is a self-contained page — inline SVG, no build step, no dependencies beyond
Google Fonts. Open it directly in a browser to view it locally.

To update the published version, edit this file and republish it to the **same
URL** (passing that URL is what keeps the link stable rather than creating a
second artifact). Editing without republishing changes nothing for anyone
holding the link.

## Session transcript

`scripts/render_transcript.py` turns a raw Claude Code session log into a
readable HTML page. The raw logs live at
`~/.claude/projects/<project-slug>/<session-id>.jsonl` — faithful but
unreadable, since most records are tool results.

    uv run python -m scripts.render_transcript --list
    uv run python -m scripts.render_transcript --scan <session-id>   # secrets check
    uv run python -m scripts.render_transcript <session-id> -o transcript.html

It keeps every human turn and every reply verbatim, compacts tool calls to one
chip each, and marks idle gaps plus any interrupt/resume boundary. It refuses to
render if the secret scan finds anything.

Rendered for this build:
https://claude.ai/code/artifact/9c64c0a6-5cdd-43dd-a42c-3cad663845b7
