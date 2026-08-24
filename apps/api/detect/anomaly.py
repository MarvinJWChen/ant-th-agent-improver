"""Generic anomaly signal.

An IsolationForest over the same generic features every trace has. It is given
no rules, no labels, and no notion of what a refund failure looks like; it simply
reports which traces sit in sparse regions of feature space.

Its job in this system is to cover the failures nobody wrote a rule for. Whether
it actually does is measured offline in scripts/validate_detection.py against
held-out labels the runtime never sees.
"""
from __future__ import annotations

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

from apps.api.detect.features import TraceFeatures

CONTAMINATION = 0.12
SVD_COMPONENTS = 12
RANDOM_STATE = 7


def build_matrix(feats: list[TraceFeatures]) -> tuple[np.ndarray, TfidfVectorizer, TruncatedSVD]:
    numeric = np.array([f.vector() for f in feats], dtype=float)
    numeric = StandardScaler().fit_transform(numeric)

    vec = TfidfVectorizer(token_pattern=r"[^\s]+", min_df=3, max_features=4000)
    tfidf = vec.fit_transform([f.signature for f in feats])
    k = min(SVD_COMPONENTS, max(2, tfidf.shape[1] - 1))
    svd = TruncatedSVD(n_components=k, random_state=RANDOM_STATE)
    reduced = StandardScaler().fit_transform(svd.fit_transform(tfidf))

    return np.hstack([numeric, reduced]), vec, svd


def score(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Return per-trace anomaly scores in [0,1] (higher = more anomalous) and the cut."""
    forest = IsolationForest(
        n_estimators=300,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    forest.fit(matrix)
    raw = -forest.score_samples(matrix)  # higher = more anomalous
    lo, hi = float(raw.min()), float(raw.max())
    norm = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)

    cut_raw = float(np.percentile(raw, 100 * (1 - CONTAMINATION)))
    cut = (cut_raw - lo) / (hi - lo) if hi > lo else 0.0
    return norm, float(cut)
