"""Generic anomaly signal.

This model is given no failure-specific rules and no labels. It knows three
things that are true of *any* agent's production traces, whatever the agent
does:

1. **Incompletion** — the agent did not finish the job itself. An escalation or
   an abandonment is a cost event on every support platform ever built.
2. **Peer-relative cost** — this trace took far more turns, time, tool calls,
   retries or errors than other traces handling the same kind of request.
3. **Shape isolation** — the trace sits in a sparse region of feature space, so
   it does not resemble how this agent usually behaves at all.

None of those mention refunds, emails, or SLAs. That is the point: the signal
has to cover failures nobody wrote a rule for. It is deliberately high-recall
and low-precision — its job is to decide what is worth clustering, and the
clustering step is what turns a noisy flagged set into coherent patterns.

How well it actually works is measured offline against held-out family labels
that this module has no access to. See scripts/validate_detection.py.
"""
from __future__ import annotations

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

from apps.api.detect.features import TraceFeatures

SVD_COMPONENTS = 12
RANDOM_STATE = 7
FLAG_PERCENTILE = 78.0  # flag roughly the top fifth for clustering

W_INCOMPLETION = 0.45
W_COST = 0.35
W_ISOLATION = 0.20

COST_FEATURES = [
    "turns",
    "log_duration",
    "n_tool_calls",
    "n_errors",
    "n_timeouts",
    "max_repeat_identical_call",
]


def build_matrix(feats: list[TraceFeatures]) -> tuple[np.ndarray, TfidfVectorizer, TruncatedSVD]:
    numeric = StandardScaler().fit_transform(np.array([f.vector() for f in feats], dtype=float))
    vec = TfidfVectorizer(token_pattern=r"[^\s]+", min_df=3, max_features=4000)
    tfidf = vec.fit_transform([f.signature for f in feats])
    k = min(SVD_COMPONENTS, max(2, tfidf.shape[1] - 1))
    svd = TruncatedSVD(n_components=k, random_state=RANDOM_STATE)
    reduced = StandardScaler().fit_transform(svd.fit_transform(tfidf))
    return np.hstack([numeric, reduced]), vec, svd


def _norm(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def peer_relative_cost(
    feats: list[TraceFeatures], intents: list[str], incomplete: np.ndarray
) -> np.ndarray:
    """Mahalanobis distance in cost space, standardised within intent peers.

    Comparing a trace against others handling the same kind of request is what
    stops 'this intent is just slow' from looking like a failure.
    """
    C = np.array(
        [[f.numeric.get(k, 0.0) for k in COST_FEATURES] for f in feats], dtype=float
    )
    C = np.hstack([C, incomplete.reshape(-1, 1).astype(float)])
    Z = np.zeros_like(C)
    for it in set(intents):
        m = np.array([i == it for i in intents])
        mu, sd = C[m].mean(axis=0), C[m].std(axis=0) + 1e-9
        Z[m] = (C[m] - mu) / sd
    cov = np.cov(Z.T) + np.eye(Z.shape[1]) * 1e-6
    inv = np.linalg.pinv(cov)
    d = Z - Z.mean(axis=0)
    return np.sqrt(np.einsum("ij,jk,ik->i", d, inv, d))


def shape_isolation(matrix: np.ndarray) -> np.ndarray:
    forest = IsolationForest(
        n_estimators=300, contamination="auto", random_state=RANDOM_STATE, n_jobs=-1
    )
    forest.fit(matrix)
    return -forest.score_samples(matrix)


def score(
    matrix: np.ndarray,
    feats: list[TraceFeatures],
    outcomes: list[str],
    intents: list[str],
) -> tuple[np.ndarray, float, dict[str, np.ndarray]]:
    """Return (score in [0,1], flag threshold, per-component scores)."""
    incomplete = np.array([o != "resolved" for o in outcomes])
    comp = {
        "incompletion": incomplete.astype(float),
        "cost": _norm(peer_relative_cost(feats, intents, incomplete)),
        "isolation": _norm(shape_isolation(matrix)),
    }
    combined = (
        W_INCOMPLETION * comp["incompletion"]
        + W_COST * comp["cost"]
        + W_ISOLATION * comp["isolation"]
    )
    combined = _norm(combined)
    threshold = float(np.percentile(combined, FLAG_PERCENTILE))
    return combined, threshold, comp


def explain(comp: dict[str, np.ndarray], i: int) -> str:
    bits = []
    if comp["incompletion"][i] > 0:
        bits.append("the agent did not resolve the request itself")
    if comp["cost"][i] >= 0.5:
        bits.append(f"cost {comp['cost'][i]:.2f} vs same-intent peers")
    if comp["isolation"][i] >= 0.5:
        bits.append(f"unusual trace shape ({comp['isolation'][i]:.2f})")
    return "; ".join(bits) if bits else "moderate deviation across generic features"
