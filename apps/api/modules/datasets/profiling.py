"""
AIDSE Platform — Dataset Profiling (Phase 2)

Produces the JSON profile stored on every DatasetVersion:
- schema inference & semantic types (numeric / categorical / boolean /
  datetime / identifier / text)
- row/column counts, missingness, duplicate rows, unique values
- distributions (histograms) and skew for numeric columns
- pairwise correlations between numeric columns
- constant / near-constant and high-cardinality column detection
- target candidate suggestion, class imbalance, suspicious leakage

Large datasets (> 500k rows) are sampled for statistics; this is recorded
in the profile via "profiled_on_sample".
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from apps.api.modules.datasets.ingestion import detect_format, load_dataframe

logger = logging.getLogger(__name__)

MAX_SAMPLE_ROWS = 500_000
LEAKAGE_CORRELATION_THRESHOLD = 0.95
CORRELATION_PAIR_THRESHOLD = 0.6
HIGH_CARDINALITY_THRESHOLD = 100
NEAR_CONSTANT_RATIO = 0.98


def _json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalars into strict JSON-compatible values."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
        return round(value, 6)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _infer_semantic_type(df: pd.DataFrame, col: str) -> str:
    series = df[col]

    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    lowered = str(col).strip().lower()
    name_suggests_id = lowered == "id" or lowered.endswith("_id")

    if pd.api.types.is_numeric_dtype(series):
        non_null = series.dropna()
        if len(non_null) > 0:
            unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
            if name_suggests_id or (
                pd.api.types.is_integer_dtype(series) and unique_ratio > 0.98
            ):
                return "identifier"
        return "numeric"

    # Object / string columns: try datetime detection on a small sample
    sample = series.dropna().astype(str).head(200)
    if len(sample) > 0:
        parsed = pd.to_datetime(sample, errors="coerce")
        if parsed.notna().mean() > 0.7:
            return "datetime"

    unique_count = int(series.nunique(dropna=True))
    if unique_count <= max(50, int(len(df) * 0.05)):
        return "categorical"

    if name_suggests_id or unique_count > len(df) * 0.9:
        return "identifier"

    return "text"


def _numeric_stats(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    stats: dict[str, Any] = {}
    if clean.empty:
        return stats

    q1 = float(clean.quantile(0.25))
    q3 = float(clean.quantile(0.75))
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = int(((clean < lower) | (clean > upper)).sum()) if iqr > 0 else 0

    counts, edges = np.histogram(clean, bins=min(30, max(5, clean.nunique())))
    stats.update(
        {
            "min": _json_safe(clean.min()),
            "max": _json_safe(clean.max()),
            "mean": _json_safe(clean.mean()),
            "median": _json_safe(clean.median()),
            "std": _json_safe(clean.std()),
            "skew": _json_safe(clean.skew()) if len(clean) > 2 else None,
            "outliers_count": outliers,
            "histogram": {
                "bin_edges": [_json_safe(e) for e in edges],
                "counts": [int(c) for c in counts],
            },
        }
    )
    return stats


def _categorical_stats(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    stats: dict[str, Any] = {}
    if clean.empty:
        return stats
    top = clean.value_counts().head(10)
    stats["top_values"] = {str(k): int(v) for k, v in top.items()}
    return stats


def profile_dataframe(df: pd.DataFrame, target_column: str | None = None) -> dict[str, Any]:
    """Build the full profiling payload from an already-loaded DataFrame."""
    profiled_on_sample = False
    if len(df) > MAX_SAMPLE_ROWS:
        df = df.sample(n=MAX_SAMPLE_ROWS, random_state=42)
        profiled_on_sample = True

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    profile: dict[str, Any] = {
        "num_rows": int(len(df)),
        "num_columns": int(len(df.columns)),
        "profiled_on_sample": profiled_on_sample,
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_pct": _json_safe(df.duplicated().mean() * 100),
        "columns": {},
        "correlations": [],
        "target_candidate": None,
        "target_leakage": [],
        "imbalance": {},
    }

    constant_columns: list[str] = []
    high_cardinality_columns: list[str] = []

    for col in df.columns:
        semantic = _infer_semantic_type(df, col)
        num_nulls = int(df[col].isnull().sum())
        unique_count = int(df[col].nunique(dropna=True))

        col_stats: dict[str, Any] = {
            "type": str(df[col].dtype),
            "semantic_type": semantic,
            "null_count": num_nulls,
            "null_pct": _json_safe(num_nulls / len(df) * 100) if len(df) else 0,
            "unique_count": unique_count,
            "is_constant": unique_count <= 1,
            "near_constant": False,
        }

        if col_stats["is_constant"]:
            constant_columns.append(str(col))
        elif unique_count / max(len(df), 1) >= NEAR_CONSTANT_RATIO and not df[col].isnull().any():
            col_stats["near_constant"] = True

        if semantic in ("categorical", "text") and unique_count > HIGH_CARDINALITY_THRESHOLD:
            col_stats["high_cardinality"] = True
            high_cardinality_columns.append(str(col))

        if semantic in ("numeric", "identifier"):
            col_stats.update(_numeric_stats(df[col]))
        if semantic in ("categorical", "boolean", "text"):
            col_stats.update(_categorical_stats(df[col]))
        # Low-cardinality columns of ANY type (e.g. 0/1 numeric targets) get
        # value counts so the task detector can judge class balance.
        if 0 < unique_count <= 10 and "top_values" not in col_stats:
            clean = df[col].dropna()
            if not clean.empty:
                col_stats["top_values"] = {
                    str(k): int(v) for k, v in clean.value_counts().head(10).items()
                }

        profile["columns"][str(col)] = col_stats

    # ── Pairwise correlations among numeric columns ────────────────────────
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        pairs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for a in numeric_cols:
            for b in numeric_cols:
                if a >= b:
                    continue
                key = (a, b)
                if key in seen:
                    continue
                seen.add(key)
                r = corr_matrix.loc[a, b]
                if pd.notna(r) and abs(r) >= CORRELATION_PAIR_THRESHOLD:
                    pairs.append(
                        {"a": a, "b": b, "r": _json_safe(r)}
                    )
        pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
        profile["correlations"] = pairs[:15]

    # ── Target candidate (when user has not chosen one) ─────────────────────
    from apps.api.modules.datasets.ingestion import sniff_target_candidate

    effective_target = target_column
    if not effective_target:
        candidate = sniff_target_candidate(df)
        if candidate and candidate.get("confidence") in ("name_match", "heuristic"):
            profile["target_candidate"] = candidate
            effective_target = candidate["column"]
            if candidate["confidence"] == "heuristic":
                # Do not run leakage/imbalance off a weak guess; surface only.
                effective_target = None

    # ── Leakage & imbalance against an explicit/confirmed target ───────────
    if effective_target and effective_target in df.columns:
        if effective_target in numeric_cols:
            corr_matrix = df[numeric_cols].corr()
            target_corrs = corr_matrix[effective_target].drop(
                effective_target, errors="ignore"
            )
            for other_col, corr_val in target_corrs.items():
                if pd.notna(corr_val) and abs(corr_val) > LEAKAGE_CORRELATION_THRESHOLD:
                    profile["target_leakage"].append(
                        {
                            "column": other_col,
                            "correlation": _json_safe(corr_val),
                            "warning": (
                                "Extremely high correlation with target — potential "
                                "data leakage. Verify this feature exists at prediction time."
                            ),
                        }
                    )

        identifier_like = [
            c for c, s in profile["columns"].items()
            if s["semantic_type"] == "identifier" and c != effective_target
        ]
        if identifier_like:
            profile["target_leakage"].append(
                {
                    "column": identifier_like,
                    "warning": (
                        "Identifier-like columns should be excluded from model "
                        "features — models memorize them instead of learning patterns."
                    ),
                }
            )

        task_type = (
            "regression"
            if pd.api.types.is_numeric_dtype(df[effective_target])
            and df[effective_target].nunique(dropna=True) > 20
            else "classification"
        )
        if task_type == "classification":
            target_counts = df[effective_target].value_counts(normalize=True)
            if len(target_counts) > 1 and target_counts.min() < 0.05:
                profile["imbalance"] = {
                    "severity": "critical",
                    "warning": "Highly imbalanced target class detected (< 5% minority share).",
                    "distribution": {
                        str(k): _json_safe(v) for k, v in target_counts.items()
                    },
                }
            elif len(target_counts) > 1 and target_counts.min() < 0.20:
                profile["imbalance"] = {
                    "severity": "info",
                    "warning": "Mildly imbalanced target classes (< 20% minority share).",
                    "distribution": {
                        str(k): _json_safe(v) for k, v in target_counts.items()
                    },
                }

    # ── Quality issue summary (feeds the Data Quality Center) ──────────────
    cols = profile["columns"]
    missing_cols = sum(1 for s in cols.values() if s["null_count"] > 0)
    outlier_total = sum(int(s.get("outliers_count") or 0) for s in cols.values())
    profile["quality_issues_summary"] = {
        "critical": (
            int(profile["duplicate_rows"] > 0)
            + sum(1 for l in profile["target_leakage"])
            + (1 if profile["imbalance"].get("severity") == "critical" else 0)
            + (len(constant_columns) > 0)
        ),
        "warning": missing_cols + len(high_cardinality_columns) + (outlier_total > 0),
        "info": len(constant_columns),
        "has_missing_columns": missing_cols,
        "has_outliers": outlier_total > 0,
        "constant_columns": constant_columns,
        "high_cardinality_columns": high_cardinality_columns,
    }

    return profile


def profile_dataset_file(file_path: str, target_column: str | None = None) -> dict[str, Any]:
    """
    Profile any supported dataset file (CSV/XLSX/XLS).
    Returns {"error": ...} payload instead of raising so uploads never 500.
    """
    try:
        fmt = detect_format(file_path)
        df = load_dataframe(file_path, fmt)
    except Exception as exc:
        logger.error("Failed to load dataset file %s: %s", file_path, exc)
        return {"error": str(exc)}

    try:
        profile = profile_dataframe(df, target_column=target_column)
        profile["format"] = fmt.lstrip(".")
        return profile
    except Exception as exc:  # Defensive: profiling must never crash an upload
        logger.exception("Profiling failed for %s", file_path)
        return {"error": f"Profiling failed: {exc}"}
