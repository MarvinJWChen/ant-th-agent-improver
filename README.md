# Agent Improver

**Production-trace-driven agent improvement with side-effect-safe counterfactual replay.**

Managed agents produce thousands of traces, but improving them is still manual: read a
few complaints, try a prompt change, ship it on thin evidence. Offline test sets miss the
failures that only appear with real users, real tools, and real state.

Agent Improver closes that loop. It treats production traces as evaluation data — finding
recurring failures, explaining them with cited evidence, generating a bounded remediation,
and **proving the fix against the same frozen starting conditions before it can ship**.

Live demo: **https://agent-improver.onrender.com**

The demo domain is a customer-support refund agent with 1,000 synthetic production traces,
seeded with three recurring failures: an erroneous second refund caused by ambiguous status
and execution tools; duplicate confirmation emails after a timeout and retry; and premature
human escalation while a refund is still processing.

---

## The journey

| Step | What happens |
|---|---|
| **Agents** | Pick the managed agent whose production traffic is being observed |
| **Agent** | 1,000 traces, outcome mix, and the tool surface with each tool's declared blast radius |
| **Discover** | Detection runs over every trace on the spot — featurisation, anomaly scoring, clustering |
| **Investigate** | Trace evidence, then an LLM diagnosis naming the mechanism and the kind of fix required |
| **Improve** | Config-remediable patterns get patch → replay → gate → promote. Everything else gets a written proposal |

## Quickstart

```bash
uv sync
uv run python -m scripts.seed --fresh          # 1,000 traces + frozen worlds, deterministic
cd apps/web && npm ci && npm run build && cd ../..
uv run uvicorn apps.api.main:app --port 8000   # → http://localhost:8000
```

The whole journey works **with no API key**: model-dependent outputs are served from
committed captures. Export `ANTHROPIC_API_KEY` to enable the "run live" half of each
control. `scripts/capture.py` regenerates the captures from real inference.

---

## How it works

### Discovery is family-agnostic

No evaluator anywhere in the pipeline mentions refunds, emails, or SLAs — the seeded
failures have to be recovered from behaviour alone, which is the only reason recovering
them proves anything. Two signals feed clustering:

- **Observable failure signals** — the agent didn't finish, an effect repeated at one
  target, an effect issued at a target already read as finished, a retry after an
  ambiguous timeout.
- **A generic anomaly model** — incompletion, cost relative to same-intent peers, and
  shape isolation over the full feature matrix.

Their union is a deliberately high-recall *review queue*, not a failure count. Clustering
(Ward, k chosen by an elbow rule on silhouette) turns it into coherent patterns, and the
diagnosis decides which are genuine failures — including returning **"expected behaviour,
no remediation"** for clusters that are merely uncommon and correct.

### Replay is two clones of one frozen world

The baseline reproduces what production actually did. The candidate is **re-executed**,
because a changed configuration may call different tools in a different order — so the
original trace's model outputs cannot evaluate it.

Each arm gets a byte-for-byte copy of the frozen world. Every tool call dispatches through
a single host that reads and writes only the clone. Effects that would leave the boundary —
money movement, customer email — are **never executed**; they are recorded `SHADOWED` in an
Effect Ledger and simulated on the clone so the trajectory can continue. A tool the effect
registry does not know about **aborts the run**: an undeclared blast radius cannot be
bounded, so it fails closed. There is no mail, payment, or HTTP client anywhere in the
replay package, and a test asserts their absence.

### Captures are evidence, not fixtures

Cached mode is the default so the demo runs without credentials. That is only defensible if
a cached output can prove it came from a real run of the same program, so eleven fields —
task version, model, prompt, inputs, output schema, agent config, tools, corpus, world, and
agent-loop version — are hashed at capture time and recomputed at load time. Any mismatch
marks the capture stale; for replay evidence the run refuses to start at all.

### Promotion is gated, with no override

Four checks, all of which must pass:

1. **Target improvement** — the failure it was written to fix is measurably reduced
2. **Control preservation** — nothing that passed at baseline now fails, and autonomous
   resolution on the control cohort is preserved
3. **Effect safety** — zero unsafe effects, zero external calls executed
4. **Provenance** — every capture backing the candidate still validates

Patches are bounded to the system prompt and tool *descriptions*. Anything touching tool
names or input schemas is rejected before it can become a candidate — the moment a patch
can change the tool surface, the registry replay depends on stops describing reality.

---

## Real, captured, or synthetic

| Component | Status |
|---|---|
| Trace corpus and frozen worlds | **Synthetic** — deterministic generator, seed 1337 |
| Featurisation, signals, anomaly, clustering | **Real** — computed per request |
| Diagnoses, proposals, config patches | **Captured** from real `claude-opus-5` runs of the same task modules the live buttons call |
| Baseline replay | **Real** — deterministic execution against a clone |
| Counterfactual run | A captured live run's trajectory, **re-executed** against a fresh clone |
| Effect Ledger, metrics, gate, promotion | **Real** — always computed from clone state, never stored |

## Validation

```bash
uv run pytest tests/ -q                              # 39 checks
uv run python -m scripts.validate_detection          # graded against held-out labels
uv run python -m scripts.smoke_journey <base-url>    # walks every CTA
```

Current results: **recall 1.00 on all three seeded families**, weighted cluster purity
**0.88**, and an ablation showing the anomaly model alone still recovers two of the three
with every observable signal removed.

The family labels live in a database no runtime module can reach — a leakage check greps
for quoted references and fails if any runtime module names one. Two other guards exist
because they caught real bugs: capture-input determinism (set iteration order once made
pattern signatures vary between processes, silently invalidating every capture) and capture
freshness (widening a contract by one field changed the hashed inputs and dropped the whole
app back to fixtures).

## Layout

```
apps/api/detect/     featurisation, observable signals, anomaly model, clustering
apps/api/llm/        versioned tasks, schemas, provenance capture and validation
apps/api/replay/     world cloning, tool host, Effect Ledger, both arms, metrics
apps/api/gate.py     the four promotion checks
apps/api/patch/      the candidate-edit boundary
apps/web/            React SPA — the five-step journey
scripts/             corpus generator, capture pipeline, validation, smoke test
fixtures/captures/   155 provenance-stamped capture artifacts
```

`SCHEMA.md` is the authoritative data contract. `DEMO.md` is the presenter script.
`DEPLOY.md` covers the Render deployment. `docs/architecture.html` is a diagrammed
walkthrough of the system.

## Known limits

- **The world does not react.** The candidate re-executes against a static first customer
  message, so it can take a different path but the customer never responds differently to
  what it said. This is the ceiling on the methodology — replay complements shadow traffic
  and A/B testing rather than replacing them.
- **Shadowed effects always succeed.** Suppressed external calls return success, so the
  evaluation is optimistic by construction; a candidate that handles failures badly looks
  like one that handles them well.
- **Cohorts are small.** Twelve target and twelve control traces, with no confidence
  intervals on the metric deltas.
- **One cluster mixes.** Duplicate confirmations and safe retries differ only by an
  idempotency key, which the current featurisation barely reads.
- **The registry is a declaration, not a proof.** Effect classes are enforced in-process.
  A production deployment would enforce them at the sandbox boundary — deny-by-default
  egress — rather than by convention.

Deliberate non-goals: no auth, no tenancy, no real connectors, no durable workflow
infrastructure.
