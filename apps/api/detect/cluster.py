"""Clustering the flagged traces into recurring patterns.

The grouping is unsupervised and the descriptions are derived, not authored: a
cluster's headline comes from whichever features and signature tokens separate
it most sharply from the rest of the flagged population. Nothing here maps a
cluster onto a known failure family, and nothing here decides what kind of fix
it needs — that is the diagnosis step's job.
"""
from __future__ import annotations

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score

from apps.api.detect.features import NUMERIC_FEATURES, TraceFeatures

K_RANGE = (3, 4, 5, 6, 7, 8)

# Silhouette rises monotonically with k on this data, so "best silhouette" would
# always pick the largest k and shatter coherent behaviours into fragments.
# Take the smallest k that is nearly as good as the best instead — the standard
# elbow reading, and the one that keeps a pattern card meaningful.
SILHOUETTE_TOLERANCE = 0.92

# Generic, tool-level phrasing for numeric features. No failure family appears
# here — these are descriptions of trace shape.
_PHRASE = {
    "max_repeat_identical_call": "the same call repeated with identical arguments",
    "max_repeat_tool": "one tool called repeatedly",
    "n_timeouts": "tool timeouts",
    "n_errors": "tool errors",
    "has_escalation": "escalation to a human",
    "n_external_calls": "external-effect calls",
    "turns": "model turns",
    "log_duration": "long traces",
    "n_tool_calls": "many tool calls",
    "n_distinct_tools": "a wide tool surface",
    "log_max_tool_latency": "a slow tool call",
}


def _phrase(name: str, high: bool) -> str:
    if name.startswith("n_") and name[2:] not in ("timeouts", "errors", "tool_calls",
                                                  "distinct_tools", "external_calls"):
        tool = name[2:]
        return f"{'repeated' if high else 'no'} `{tool}` calls"
    base = _PHRASE.get(name, name)
    if name == "log_duration":
        return "long traces" if high else "unusually short traces"
    if name == "turns":
        return "many model turns" if high else "very few model turns"
    return base if high else f"no {base}"


def _token_phrase(tok: str) -> str:
    if tok.startswith("res:"):
        _, tool, kv = tok.split(":", 2)
        return f"`{tool}` returns {kv}"
    if tok.startswith("err:"):
        parts = tok.split(":")
        return f"`{parts[1]}` fails with {parts[-1]}"
    if tok.startswith("call:"):
        return f"calls `{tok.split(':', 1)[1]}`"
    if tok.startswith("intent:"):
        return f"intent {tok.split(':', 1)[1]}"
    return tok


def choose_k(matrix: np.ndarray) -> tuple[int, float, np.ndarray]:
    scored: list[tuple[int, float, np.ndarray]] = []
    for k in K_RANGE:
        if matrix.shape[0] <= k + 1:
            continue
        labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(matrix)
        if len(set(labels)) < 2:
            continue
        scored.append((k, float(silhouette_score(matrix, labels)), labels))
    if not scored:  # degenerate corpus
        return 1, 0.0, np.zeros(matrix.shape[0], dtype=int)
    best_sil = max(s for _, s, _ in scored)
    for k, s, labels in scored:  # K_RANGE is ascending, so this is the smallest
        if s >= SILHOUETTE_TOLERANCE * best_sil:
            return k, s, labels
    return scored[-1]


def describe(
    labels: np.ndarray,
    cluster_id: int,
    feats: list[TraceFeatures],
) -> tuple[str, str, list[str]]:
    """Return (title, signature, top_features) derived from what separates this cluster."""
    idx = np.where(labels == cluster_id)[0]
    others = np.where(labels != cluster_id)[0]
    if len(idx) == 0:
        return "Empty cluster", "", []

    mine = np.array([feats[i].vector() for i in idx], dtype=float)
    rest = (
        np.array([feats[i].vector() for i in others], dtype=float)
        if len(others)
        else np.zeros((1, mine.shape[1]))
    )
    mu_m, mu_r = mine.mean(axis=0), rest.mean(axis=0)
    sd = np.concatenate([mine, rest]).std(axis=0) + 1e-9
    lift = (mu_m - mu_r) / sd

    order = np.argsort(-np.abs(lift))[:6]
    top_features = [
        f"{NUMERIC_FEATURES[i]}={mu_m[i]:.2f} (cohort {mu_r[i]:.2f})" for i in order[:4]
    ]

    # Signature tokens: those far more common inside the cluster than outside.
    def token_freq(indices):
        counts: dict[str, int] = {}
        for i in indices:
            for t in set(feats[i].signature.split()):
                counts[t] = counts.get(t, 0) + 1
        n = max(len(indices), 1)
        return {t: c / n for t, c in counts.items()}

    fin, fout = token_freq(idx), token_freq(others) if len(others) else {}
    # Tie-break on the token itself. Without it, equally distinctive tokens are
    # ordered by dict insertion, which follows set iteration order and therefore
    # varies between processes — enough to change a pattern's signature text and
    # invalidate every capture keyed on it.
    distinctive = sorted(
        ((t, f - fout.get(t, 0.0)) for t, f in fin.items() if f >= 0.6),
        key=lambda kv: (-kv[1], kv[0]),
    )[:3]

    sig_parts = [_token_phrase(t) for t, _ in distinctive]
    feat_parts = [_phrase(NUMERIC_FEATURES[i], lift[i] > 0) for i in order[:2]]

    signature = " · ".join(sig_parts) if sig_parts else " · ".join(feat_parts)
    headline = ", ".join(dict.fromkeys(sig_parts[:2] + feat_parts[:1]))
    title = headline[0].upper() + headline[1:] if headline else f"Cluster {cluster_id}"
    return title, signature, top_features
