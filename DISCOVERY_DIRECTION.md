# M3 direction: discovery must be family-agnostic

Recorded 2026-08-24, from the user. **Not yet implemented** — M1 (browser journey)
comes first. This supersedes the two bespoke evaluators currently in
`apps/api/detect/evaluators.py`.

## Required pipeline

```
1,000 traces
  → generic featurization
  → [observable failure/escalation signals  ∪  generic anomaly score]
  → suspicious traces
  → unsupervised clustering
  → pattern cards   (expected to recover the 3 seeded patterns)
```

## Permitted signals (generic only)

latency · turns · explicit failure/escalation outcomes · timeouts · retries ·
repeated calls · repeated effects · tool-event sequences

## Forbidden in the runtime pipeline

No evaluator may encode double refunds, duplicate emails, slow refunds, or any
other family-specific notion. Concretely, this means deleting
`evaluators.double_refund` and `evaluators.duplicate_confirmation` and replacing
them with generic observable-failure signals — e.g. "the same effect-producing
call was issued twice against the same target", "a tool timed out and was
retried", "the agent did not resolve the request itself" — which happen to catch
those families without naming them.

## Labels

`var/hidden_labels.db` stays entirely outside the runtime pipeline. It is read
only afterwards, by `scripts/validate_detection.py`, to measure per-family
recall and cluster purity.

## Status at the time this was recorded

With the two bespoke evaluators still present: recall 1.00 on all three
families; F1 and F2 clusters 100% pure; the F3 cluster is 130 traces at 54%
purity (F3 mixed with justified escalations). The generic-only rewrite must hold
recall and should improve F3 cluster separation.
