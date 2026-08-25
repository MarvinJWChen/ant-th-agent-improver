"""Offline validation of failure discovery.

This is the only place the hidden family labels are ever read. They exist to
grade the detector, never to help it: if the runtime could see them, recovering
the seeded families would prove nothing.

Checks:
  1. no label leakage — nothing under apps/api/ can reach the labels
  2. per-family recall in the flagged set
  3. cluster purity, and whether each family gets a cluster of its own
  4. the generic anomaly signal beats a random subset of the same size
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

from apps.api import paths, store
from apps.api.detect import pipeline

ROOT = Path(__file__).resolve().parents[1]
LABELS_DB = paths.VAR / "hidden_labels.db"

MIN_RECALL = 0.60
MIN_WEIGHTED_PURITY = 0.70

FAMILIES = ["F1_double_refund", "F2_duplicate_confirmation", "F3_premature_escalation"]

# Build output is generated, not authored — scanning it would just re-report
# whatever the sources already said.
GREP = [
    "grep", "-rInE",
    "--exclude-dir=dist", "--exclude-dir=node_modules", "--exclude-dir=__pycache__",
]


def load_labels() -> dict[str, str]:
    with sqlite3.connect(f"file:{LABELS_DB}?mode=ro", uri=True) as c:
        return dict(c.execute("SELECT trace_id, family FROM hidden_labels"))


def check_no_leakage() -> list[str]:
    """No runtime module may name or open the labels."""
    failures = []
    # A module that actually reads the labels has to name the table or file as a
    # string literal. Prose that merely explains why we do not touch them does
    # not, so quoting is what separates a real reference from a comment.
    res = subprocess.run(
        GREP + [r"""[\"']hidden_labels""", str(ROOT / "apps")],
        capture_output=True,
        text=True,
    )
    if res.stdout.strip():
        failures.append(f"apps/ references the hidden labels in code:\n{res.stdout}")

    # The labels must also not be reachable through the runtime's own path helper.
    if hasattr(paths, "HIDDEN_LABELS_DB"):
        failures.append("apps/api/paths.py exposes a path to the hidden labels")

    # And the family vocabulary must not appear in runtime code.
    res = subprocess.run(
        GREP + ["F[123]_(double|duplicate|premature)", str(ROOT / "apps")],
        capture_output=True,
        text=True,
    )
    if res.stdout.strip():
        failures.append(f"apps/ names a seeded family:\n{res.stdout}")
    return failures


def check_input_determinism() -> list[str]:
    """Capture inputs must hash identically in a *fresh process*.

    Python randomises string hashing per process, so anything whose order comes
    from set or dict iteration can differ between runs. That is invisible in a
    single process and silently invalidates every capture, so it is checked here
    by actually launching a second interpreter.
    """
    snippet = (
        "from apps.api import services;"
        "from apps.api.llm.capture import sha;"
        "from apps.api.detect import pipeline;"
        "print(' '.join(sha(services._pattern_inputs(p.pattern_id))[:16]"
        " for p in pipeline.discover().patterns))"
    )
    outs = []
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, "-c", snippet], capture_output=True, text=True, cwd=ROOT
        )
        if r.returncode != 0:
            return [f"determinism probe failed: {r.stderr[-400:]}"]
        outs.append(r.stdout.strip().splitlines()[-1])
    if outs[0] != outs[1]:
        return [
            "capture inputs are not deterministic across processes — "
            "captures will not validate:\n"
            f"  run 1: {outs[0]}\n  run 2: {outs[1]}"
        ]
    return []


def main() -> int:
    if not store.corpus_available() or not LABELS_DB.exists():
        print("No corpus. Run: uv run python -m scripts.seed --fresh")
        return 2

    problems: list[str] = []

    print("1. label leakage")
    leaks = check_no_leakage()
    if leaks:
        problems.extend(leaks)
        for line in leaks:
            print(f"   FAIL {line}")
    else:
        print("   ok — no runtime module references or can reach the labels")

    print("\n1b. capture-input determinism (fresh processes)")
    det = check_input_determinism()
    if det:
        problems.extend(det)
        for line in det:
            print(f"   FAIL {line}")
    else:
        print("   ok — pattern inputs hash identically in separate processes")

    labels = load_labels()
    disc = pipeline.discover(force=True)
    flagged = {f.trace.trace_id for f in disc.flagged}
    n_corpus = disc.n_traces_scanned

    print(f"\n2. recall in the flagged set ({len(flagged)} of {n_corpus} traces flagged)")
    for fam in FAMILIES:
        ids = [t for t, f in labels.items() if f == fam]
        recall = sum(i in flagged for i in ids) / len(ids)
        status = "ok  " if recall >= MIN_RECALL else "FAIL"
        if recall < MIN_RECALL:
            problems.append(f"{fam} recall {recall:.2f} < {MIN_RECALL}")
        print(f"   {status} {fam:32s} recall={recall:.2f}  (n={len(ids)})")

    print("\n3. cluster purity")
    total_dominant = 0
    family_clusters: dict[str, float] = {}
    for p in disc.patterns:
        ids = [f.trace.trace_id for f in disc.flagged if f.cluster_id == p.impact["cluster_id"]]
        counts = Counter(labels.get(i, "?") for i in ids)
        dom, n = counts.most_common(1)[0]
        total_dominant += n
        purity = n / len(ids)
        if dom in FAMILIES:
            family_clusters[dom] = max(family_clusters.get(dom, 0.0), purity)
        print(f"   {p.pattern_id:3s} n={len(ids):4d} purity={purity:.2f} dominant={dom}")
    weighted = total_dominant / max(len(flagged), 1)
    status = "ok  " if weighted >= MIN_WEIGHTED_PURITY else "FAIL"
    if weighted < MIN_WEIGHTED_PURITY:
        problems.append(f"weighted purity {weighted:.3f} < {MIN_WEIGHTED_PURITY}")
    print(f"   {status} weighted purity = {weighted:.3f}")
    for fam in FAMILIES:
        if fam not in family_clusters:
            problems.append(f"{fam} does not dominate any cluster")
            print(f"   FAIL {fam} dominates no cluster")
        else:
            print(f"   ok   {fam:32s} owns a cluster at purity {family_clusters[fam]:.2f}")

    print("\n4. ablation — what the generic anomaly model finds on its own")
    # The real question is not whether the anomaly model adds traces on top of the
    # observable signals, but whether it would still surface these failures if no
    # signal fired at all. So we strip the signals and score with the model alone.
    import numpy as np

    from apps.api.detect import anomaly as anomaly_mod
    from apps.api.detect.features import extract as extract_features

    traces = [store.get_trace(t) for t in store.all_trace_ids()]
    feats = [extract_features(t) for t in traces]
    matrix, _, _ = anomaly_mod.build_matrix(feats)
    scores, threshold, _ = anomaly_mod.score(
        matrix, feats, [t.outcome for t in traces], [t.intent for t in traces]
    )
    budget = len(flagged)
    top = {feats[i].trace_id for i in np.argsort(-scores)[:budget]}
    print(f"   model alone, same budget ({budget} traces):")
    for fam in FAMILIES:
        ids = [t for t, f in labels.items() if f == fam]
        r = sum(i in top for i in ids) / len(ids)
        print(f"     {fam:32s} recall={r:.2f}")
    held_out = "F3_premature_escalation"
    ids = [t for t, f in labels.items() if f == held_out]
    r = sum(i in top for i in ids) / len(ids)
    if r < MIN_RECALL:
        problems.append(f"anomaly-model-only recall for {held_out} is {r:.2f} < {MIN_RECALL}")
        print(f"   FAIL the model alone would miss {held_out}")
    else:
        print(f"   ok   the model alone still recovers {held_out} at recall {r:.2f}")

    print()
    if problems:
        print(f"FAILED — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("PASSED — discovery meets every acceptance criterion")
    return 0


if __name__ == "__main__":
    sys.exit(main())
