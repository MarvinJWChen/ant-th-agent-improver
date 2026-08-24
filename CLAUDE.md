# Time-boxed demo rules

Success means the complete narrated browser flow works. Optimize for visible
outcomes and truthful technical claims, not production completeness.

## Execution

- Deliver a complete fixture-backed browser journey within the first 35 minutes.
- Every audience-facing CTA must work, be clearly simulated, or be absent.
- Replace fixtures incrementally behind stable UI-facing contracts; keep P0 runnable.
- The primary agent owns the browser path, integration, and final acceptance.
- Delegate only bounded, independent work with explicit outputs and non-overlapping
  ownership.
- If blocked for 15 minutes, reduce scope or preserve the contract with a fixture.
  Do not fixture cluster assignments, replay effects, computed metrics,
  provenance decisions, or promotion results in the final demo.
- Avoid speculative abstractions, generic frameworks, production hardening, and
  unrequested infrastructure.
- At each milestone report working browser actions, real versus fixture behavior,
  remaining P0 gaps, and the next cut if time slips.
- After P0 works, spend at most 60 additional minutes on the three
  technical-depth additions.
- Reserve the final 30 minutes for integration, deployment, UX, and rehearsal.

## Validation

Use only checks that protect demonstrated claims:

- one complete browser happy path covering every CTA;
- one failure-discovery and clustering check covering generic anomaly usefulness,
  the held-out family, clustering quality, and no label leakage;
- one replay-safety invariant check;
- one promotion check covering target improvement, passing controls, and zero
  unsafe external effects;
- one cached startup and provenance check requiring no API key and preventing a
  stale or incompatible capture from authorizing promotion.

Run focused checks during subsystem work and the browser check at milestone
boundaries. Do not pursue coverage targets, exhaustive edge cases, load testing,
cross-browser testing, or comprehensive production behavior. Tests passing alone
does not mean the demo is complete.

## Safety and scope

- Never place credentials in chat, source, fixtures, logs, or committed env files.
- Hidden synthetic failure-family labels are for offline validation only and
  must not be used by runtime detection, anomaly scoring, or clustering.
- When new work threatens P0, name the visible capability or final-validation time
  it displaces and recommend a cut before proceeding.
- Do not claim completion until the deployed browser path works from a fresh state.

## Git workflow

- Treat git as a recovery mechanism during development.
- Commit after each meaningful working milestone.
- Before committing:
  - run the relevant tests or smoke check;
  - inspect `git diff`;
  - do not commit secrets, `.env`, transient generated artifacts, or dependency
    caches. Sanitized, validated captures required by the default demo path may
    be committed under the designated fixtures directory.
- Use concise commit messages describing the completed milestone.
- Push to `origin` after major milestones or before risky/refactoring work.
- Do not rewrite published history or force-push unless explicitly asked.
- If the working tree already contains user changes that you did not make,
  preserve them and do not overwrite or revert them.
  