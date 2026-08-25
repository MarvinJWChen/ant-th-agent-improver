"""Failure discovery, end to end.

Two independent signals decide what is worth looking at: precise rules that
produce citable evidence, and a generic anomaly model that has no rules at all.
Their union is clustered into recurring patterns. Every number this module
returns is computed from the corpus on the request that asks for it.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from apps.api import store
from apps.api.contracts import DiscoveryResult, EvidenceHit, FlaggedTrace, PatternCard
from apps.api.detect import anomaly, cluster, evaluators
from apps.api.detect.features import extract

_CACHE: dict[str, DiscoveryResult] = {}


def discover(force: bool = False) -> DiscoveryResult:
    key = store.corpus_hash()
    if not force and key in _CACHE:
        return _CACHE[key]

    t0 = time.time()
    trace_ids = store.all_trace_ids()
    traces = [store.get_trace(t) for t in trace_ids]
    feats = [extract(t) for t in traces]

    # 1 — observable failure signals: generic, evidence-producing, family-agnostic.
    medians = evaluators.peer_medians(traces)
    rule_hits: dict[str, list[EvidenceHit]] = {}
    for t, f in zip(traces, feats):
        hits = evaluators.evaluate(t, f, medians)
        if hits:
            rule_hits[t.trace_id] = hits

    # 2 — generic anomaly over the same features every trace has.
    matrix, _, _ = anomaly.build_matrix(feats)
    scores, threshold, components = anomaly.score(
        matrix,
        feats,
        [t.outcome for t in traces],
        [t.intent for t in traces],
    )

    flagged_idx = [
        i
        for i, f in enumerate(feats)
        if f.trace_id in rule_hits or scores[i] >= threshold
    ]

    # 3 — cluster the union of everything worth looking at.
    sub = matrix[flagged_idx]
    k, silhouette, labels = cluster.choose_k(sub)
    sub_feats = [feats[i] for i in flagged_idx]

    flagged: list[FlaggedTrace] = []
    for pos, i in enumerate(flagged_idx):
        t, f = traces[i], feats[i]
        hits = list(rule_hits.get(t.trace_id, []))
        if scores[i] >= threshold:
            hits.append(
                EvidenceHit(
                    source="anomaly",
                    rule_id=None,
                    label="Anomalous trace shape",
                    detail=(
                        f"Anomaly score {scores[i]:.3f} ≥ threshold {threshold:.3f}. "
                        f"Signal: {anomaly.explain(components, i)}. No rule was involved."
                    ),
                    score=round(float(scores[i]), 3),
                )
            )
        flagged.append(
            FlaggedTrace(
                trace=t,
                hits=hits,
                anomaly_score=round(float(scores[i]), 3),
                rule_flagged=t.trace_id in rule_hits,
                cluster_id=int(labels[pos]),
            )
        )

    n_corpus = len(traces)
    patterns: list[PatternCard] = []
    for cid in sorted(set(int(x) for x in labels)):
        members = [ft for ft in flagged if ft.cluster_id == cid]
        if not members:
            continue
        title, signature, top_features = cluster.describe(labels, cid, sub_feats)
        rule_members = [m for m in members if m.rule_flagged]
        evidence = [h.detail for m in members[:6] for h in m.hits if h.source == "evaluator"][:3]
        if not evidence:
            evidence = [h.detail for m in members[:3] for h in m.hits][:3]
        exemplars = sorted(members, key=lambda m: -m.anomaly_score)[:6]
        patterns.append(
            PatternCard(
                pattern_id=f"P{cid + 1}",
                title=title,
                signature=signature,
                size=len(members),
                share_of_flagged=round(len(members) / max(len(flagged), 1), 4),
                discovered_by="evaluator+anomaly" if rule_members else "anomaly-only",
                remediation_kind=None,
                top_features=top_features,
                exemplar_trace_ids=[m.trace.trace_id for m in exemplars],
                representative_evidence=evidence,
                impact={
                    "traces": len(members),
                    "share_of_corpus": round(len(members) / max(n_corpus, 1), 4),
                    "rule_flagged": len(rule_members),
                    "anomaly_only": len(members) - len(rule_members),
                    "escalated": sum(1 for m in members if m.trace.outcome == "escalated"),
                    "cluster_id": cid,
                },
            )
        )
    patterns.sort(key=lambda p: -p.size)

    result = DiscoveryResult(
        computed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        corpus_hash=key,
        n_traces_scanned=n_corpus,
        n_flagged=len(flagged),
        n_rule_flagged=len(rule_hits),
        n_anomaly_only=sum(1 for f in flagged if not f.rule_flagged),
        anomaly_threshold=round(threshold, 4),
        cluster_k=k,
        silhouette=round(silhouette, 4),
        patterns=patterns,
        flagged=sorted(flagged, key=lambda f: -f.anomaly_score),
    )
    _CACHE[key] = result
    print(f"[discovery] {n_corpus} traces → {len(flagged)} flagged → k={k} "
          f"silhouette={silhouette:.3f} in {time.time() - t0:.1f}s")
    return result
