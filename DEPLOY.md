# Deploying to Render

The repo is already push-ready: `render.yaml` is a blueprint, `Dockerfile` is a
two-stage build (Node builds the SPA, Python serves it and the API), and both
lockfiles are committed. Render builds the image itself — no local Docker needed.

## One-time setup

1. **Render dashboard → New → Blueprint**, and pick
   `MarvinJWChen/ant-th-agent-improver` (private repo: authorise the Render
   GitHub app for it first).
2. Render reads `render.yaml` and proposes one web service, `agent-improver`,
   with health check `/api/health`.
3. It will ask for **`ANTHROPIC_API_KEY`** — the blueprint declares it
   `sync: false`, so it is never in git and must be typed into the dashboard.
   The demo works without it; setting it enables the "run live" half of each
   button pair.
4. Apply. First build takes a few minutes (npm ci + uv sync + a 1,000-trace
   seed that runs at image build time so cold starts stay fast).

## Verifying the deploy

```bash
BASE=https://agent-improver.onrender.com
curl -s $BASE/api/health           # all five subsystems must say "real"
curl -s $BASE/api/agent | grep -o '"total_traces":[0-9]*'
curl -s -o /dev/null -w '%{http_code}\n' $BASE/discovery   # SPA deep link → 200
```

Then walk the journey in `DEMO.md`. The one thing to confirm on the deployed URL
is that the **replay step runs** rather than returning 409: that proves the
committed captures still validate against the corpus regenerated inside the
container, which is what the portable world content-hash exists to guarantee.

## Notes

- **Cold starts.** On the free tier the service sleeps and takes ~30-50s to wake.
  `plan: starter` in `render.yaml` avoids that; either way, hit the URL once
  before presenting.
- **Ephemeral disk is fine.** `var/` is regenerated deterministically at build,
  so a fresh container reproduces the identical corpus, and every capture still
  validates against it.
- **Promotion is not persistent.** Promoting a candidate writes to `var/`, which
  a redeploy resets to `v1`. That is the behaviour you want between rehearsals.
  Locally, reset with `uv run python -m scripts.seed --fresh`.
