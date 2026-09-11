"""
AIDSE Platform — Outlier Intelligence (Phase 4)

Multi-method outlier detection with method-appropriate recommendations.

Methods:
- iqr               : robust fences (Q1 − 1.5·IQR, Q3 + 1.5·IQR)
- zscore            : |z| > threshold on values (assumes ~normal shape)
- isolation_forest  : multivariate-free per-column density via sklearn
- lof               : Local Outlier Factor for clustered distributions

Design rules:
- Detection NEVER mutates data; results are advisory only.
- The recommendation layer weighs feature type, distribution skew,
  outlier share and the ML task before suggesting keep/remove/cap/
  transform/scale.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("iqr", "zscore", "isolation_forest", "lof")
Z_THRESHOLD = 3.0
IQR_K = 1.5

# Shares above which "keep" stops being the default advice
MILD_OUTLIER_SHARE = 0.01   # <1% → usually keep
HEAVY_OUTLIER_SHARE = 0.05  # >5% → treatment worth discussing


def detect_outliers(series: pd.Series, method: str = "iqr") -> dict[str, Any]:
    """
    Detect outliers in a numeric series.

    Returns a JSON-serializable dict:
      { method, flagged_indices (capped sample), count, params }
    """
    clean = series.dropna()
    if clean.empty:
        return {"method": method, "count": 0, "flagged_indices": [], "params": {}}

    if method == "iqr":
        q1, q3 = float(clean.quantile(0.25)), float(clean.quantile(0.75))
        iqr = q3 - q1
        lower, upper = q1 - IQR_K * iqr, q3 + IQR_K * iqr
        mask = (series < lower) | (series > upper) if iqr > 0 else pd.Series(False, index=series.index)
        params = {"q1": _r(q1), "q3": _r(q3), "lower_fence": _r(lower), "upper_fence": _r(upper), "k": IQR_K}

    elif method == "zscore":
        mean, std = float(clean.mean()), float(clean.std())
        if std == 0 or np.isnan(std):
            mask = pd.Series(False, index=series.index)
            params = {"mean": _r(mean), "std": None, "threshold": Z_THRESHOLD}
        else:
            z = (series - mean) / std
            mask = z.abs() > Z_THRESHOLD
            params = {"mean": _r(mean), "std": _r(std), "threshold": Z_THRESHOLD}

    elif method in ("isolation_forest", "lof"):
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.neighbors import LocalOutlierFactor
        except ImportError:  # pragma: no cover - sklearn is a hard dependency
            raise
        X = clean.to_numpy().reshape(-1, 1)
        # Floor at 1% so small datasets still flag their injected extremes;
        # cap at 5% so dense data isn't over-flagged.
        contamination = min(0.05, max(0.01, len(clean) / 100_000))
        if method == "isolation_forest":
            model = IsolationForest(contamination=contamination, random_state=42)
            labels = model.fit_predict(X)          # -1 == outlier
            params = {"contamination": round(contamination, 4)}
        else:
            n_neighbors = max(5, min(20, len(clean) // 10))
            model = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
            labels = model.fit_predict(X)          # -1 == outlier
            params = {"n_neighbors": int(n_neighbors), "contamination": round(contamination, 4)}
        flagged_values = set(clean[labels == -1].index)
        mask = series.index.isin(flagged_values)

    else:
        raise ValueError(f"Unknown outlier method '{method}'. Supported: {SUPPORTED_METHODS}")

    flagged_idx = series.index[mask]
    # Cap the returned index list so responses stay small on huge datasets
    idx_cap = 500
    return {
        "method": method,
        "count": int(mask.sum()),
        "flagged_indices": [int(i) for i in flagged_idx[:idx_cap]],
        "flagged_truncated": bool(len(flagged_idx) > idx_cap),
        "params": params,
    }


def recommend_treatment(
    col_stats: dict[str, Any],
    detection: dict[str, Any],
    ml_task: str | None = None,
) -> dict[str, str]:
    """
    Rule-based treatment recommendation considering:
    distribution skew, outlier share and ML task.
    Never recommends deletion by default (Phase 4 rule).
    """
    num_rows = max(int(col_stats.get("unique_count") or 0), 1)  # fallback only
    count = int(detection.get("count") or 0)
    total = int(col_stats.get("_num_rows") or num_rows)
    share = count / total if total else 0.0
    skew = col_stats.get("skew")

    skewed = isinstance(skew, (int, float)) and abs(skew) > 1.0

    if share <= MILD_OUTLIER_SHARE:
        technique = "Keep as-is"
        reason = (
            f"Only {share * 100:.2f}% of rows are flagged. These are plausibly legitimate "
            "extreme observations; deleting them discards real signal."
        )
        alternatives = ["Cap (winsorize)", "Robust scaling"]
        risk = "A handful of extreme values can still dominate distance-based models (KNN, SVM)."
    elif skewed:
        technique = "Log / power transform"
        reason = (
            f"{share * 100:.2f}% of rows lie beyond the fences AND the column is heavily "
            "skewed. A transform compresses the tail while preserving every observation."
        )
        alternatives = ["Cap (winsorize)", "Yeo-Johnson transform", "Robust scaling"]
        risk = "Transforms complicate direct interpretation of raw units; invert after prediction if needed."
    elif share >= HEAVY_OUTLIER_SHARE:
        technique = "Investigate before treating"
        reason = (
            f"{share * 100:.2f}% of rows are flagged — this is too many to be random noise. "
            "The 'outliers' may be a separate population or a measurement-unit problem."
        )
        alternatives = ["Segment analysis", "Cap at percentiles (1%/99%)", "Robust scaling"]
        risk = "Mass-treatment without investigation can erase the most informative structure in the data."
    else:
        technique = "Cap at IQR fences (winsorize)"
        reason = (
            f"{share * 100:.2f}% of rows sit outside the fences with an otherwise "
            "well-behaved distribution; capping limits their leverage without dropping rows."
        )
        alternatives = ["Remove flagged rows", "Robust scaling", "Keep as-is"]
        risk = "Capping flattens genuine extremes — confirm they are errors, not events."

    if ml_task == "regression" and share > MILD_OUTLIER_SHARE:
        risk += " For regression, extreme targets also inflate RMSE — consider Huber loss instead of row removal."

    return {
        "technique": technique,
        "alternatives": alternatives,
        "reason": reason,
        "risk": risk,
    }


def scan_numeric_columns(df: pd.DataFrame, ml_task: str | None = None) -> list[dict[str, Any]]:
    """
    Scan all numeric columns with the default method (IQR) and attach
    recommendations. Cheap first pass for the UI table; per-column deep
    dives use detect_outliers() directly with other methods.
    """
    results: list[dict[str, Any]] = []
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        stats = df[col]
        clean = stats.dropna()
        if clean.empty:
            continue
        q1, q3 = float(clean.quantile(0.25)), float(clean.quantile(0.75))
        iqr = q3 - q1
        lower, upper = q1 - IQR_K * iqr, q3 + IQR_K * iqr
        count = int(((clean < lower) | (clean > upper)).sum()) if iqr > 0 else 0
        col_stats = {
            "_num_rows": int(len(clean)),
            "skew": float(clean.skew()) if len(clean) > 2 else None,
            "unique_count": int(clean.nunique()),
        }
        detection = {"method": "iqr", "count": count}
        results.append(
            {
                "column": col,
                "count": count,
                "share_pct": round(count / len(clean) * 100, 2) if len(clean) else 0,
                "lower_fence": _r(lower),
                "upper_fence": _r(upper),
                "recommendation": recommend_treatment(col_stats, detection, ml_task),
            }
        )
    results.sort(key=lambda r: r["count"], reverse=True)
    return results


def _r(v: Any, digits: int = 4) -> Any:
    """Round floats for JSON; pass through non-numerics."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        v = float(v)
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, digits)
    return v
