# Demo script

Five screens, one forward action each. Roughly four minutes at a walking pace.

## Resetting between rehearsals

A run ends with a promoted configuration. **Reset demo** in the top-right bar
restores the baseline: it drops the generated candidates, clears the replay runs
and deletes the world clones, then reloads. It leaves the trace corpus, the
frozen worlds and the captures alone — those took real inference to produce.
Click once to arm, once to confirm.

## Before you start

```bash
uv run python -m scripts.seed            # no-op if var/ already exists
ANTHROPIC_API_KEY=$(cat ~/.anthropic_key) uv run uvicorn apps.api.main:app --port 8000
```

Drop the key to demo the default path exactly as a fresh deployment sees it: the
right-hand button of every pair greys out, everything else is unchanged. The
whole journey works with no key at all — that is the point of the captures.

---

## 0 — Agents

Landing screen lists the managed agents this workspace watches. Click into
`support-refund-agent`.

*"This is an agent already running in production. We're not building it — we're
looking at how it has actually behaved."*

## 1 — Agent overview

*"Every trace this agent has produced."*

1,000 traces. ~84% self-resolved. Point at the tool table: **every tool declares
a blast radius.** `refund_execute` and `send_email` are `external` — they move
money and contact customers. That declaration is what makes replay safe later.

Then the honest framing: aggregate health looks fine. Nothing here tells you
whether the failures are one recurring bug or 160 unrelated ones.

> **Discover failure patterns →**

## 2 — Discovery

Clustering runs on the request — about half a second over all 1,000 traces.

Two signals, neither of which knows what a refund is:
- four **generic observable signals** (didn't finish, effect repeated at one
  target, effect issued at a target already read as finished, retry after an
  ambiguous timeout)
- a **generic anomaly model** (incompletion, cost vs same-intent peers, shape
  isolation)

Worth saying out loud: *no evaluator anywhere in this pipeline mentions refunds,
emails, or SLAs.* The seeded failures have to be recovered from behaviour alone.
Offline validation against held-out labels: **recall 1.00 on all three seeded
families, weighted cluster purity 0.88.**

> **Investigate →** on the escalation pattern

## 3 — Investigate

Expand an exemplar trace — real recorded events, real tool payloads.

> **Show captured diagnosis**

It names the mechanism: the system prompt escalates on *"if a customer seems
frustrated"* — a subjective trigger — while the tools already return an
objective `sla_breached` flag it never consults.

Click the provenance badge. The capture is bound by hash to this exact prompt,
these inputs, this agent config, this tool surface, and this corpus. Change any
one and it stops validating.

**Optional detour worth taking:** go back and open the 60-trace cluster that sits
next to this one. Its diagnosis returns **expected behaviour — no remediation**.
Those are escalations *after* a genuine SLA breach, and the system says so
instead of inventing a defect. Clustering finds behaviours; deciding which are
problems is a separate judgement.

> **Improve this pattern →**

## 4 — Improve (replay & gate)

Every pattern has exactly one Improve destination, and the diagnosis decides what
it is. This one is config-remediable, so Improve is patch → replay → gate →
promote. **Show captured patch**, then evaluate the **broad** candidate first. It fixes the target failure — and the gate
**blocks it**, naming the control traces it broke.

Then the **surgical** candidate. All four checks green, Promote enables.

What to point at:
- **World isolation** — each arm gets its own file copy. Same hash at start
  (identical world), different hash after (different effects). Source world
  verified unchanged.
- **Effect Ledger** — `refund_execute` and `send_email` are `SHADOWED`. Never
  executed. There is no connector in the codebase to execute them with.
- **Trajectories** — the candidate is *re-executed*, not replayed. The
  highlighted call is where it stopped following the recording and sent a delay
  notice instead of escalating.

> **Promote** → config version bumps

## 5 — Improve, for a pattern configuration cannot fix

Go back to Discovery and investigate the email-timeout pattern. Its diagnosis
returns `code`, so its Improve step is a written proposal instead: a unified diff
adding an idempotency key to the email tool. Another pattern returns `process`,
with owners and metrics.

*"A patch that only changes what the agent is told can be proven against a
frozen world. A change to tool code or to an on-call process cannot, so
promoting it automatically would be claiming evidence we don't have."*

---

## If someone asks

**"43% of traces were flagged — is the agent really that broken?"** No. That is
a high-recall review queue, not a failure count: both signals are tuned to miss
nothing, and separating real failures from rare-but-correct behaviour is what the
clustering and diagnosis do next. Three of the six clusters are failures.

**"Is the clustering real or did you hardcode three patterns?"** Hit *Re-run
detection*. It recomputes. Also `scripts/validate_detection.py` grades it
against labels the runtime cannot reach.

**"Is the cached mode just fixtures?"** Every capture is the output of the same
versioned task module the live button calls, stamped with the provenance of the
run that produced it. Bump a task version and the captures stop validating —
that is what `tests/test_cached_provenance.py` proves, field by field.

**"Could the replay email a real customer?"** There is no mail client, HTTP
client, or socket anywhere in `apps/api/replay/` — a test asserts their absence.
An unregistered tool aborts the run rather than being guessed at.

**"You compared a replay against a live run — isn't that unfair?"** Yes, they are
different execution modes, deliberately. The baseline is what production
actually did; the candidate is what the patched agent would do. Both are scored
by the same function reading the same kind of artifact: the final state of that
arm's clone plus its ledger.
