"""
AIDSE Platform — Data Quality Rules Engine (Phase 3)

Turns a stored dataset profile (profiling.py output) into structured,
human-explained quality issues grouped by severity:

    CRITICAL — corrupts model training or signals leakage
    WARNING  — degrades quality; should be addressed before ML
    INFO     — cosmetic / situational; review when relevant

Each issue carries: affected columns, affected count/pct, detection method,
why it matters, and a rule-based recommendation with alternatives + reasoning.

This is the deterministic layer of the hybrid recommendation engine:
the LLM explanation layer (Phase 6) only narrates what is computed here.
"""
from __future__ import annotations

from typing import Any

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

SKEWED_THRESHOLD = 1.0          # |skew| above this counts as skewed
MISSING_CRITICAL_PCT = 50.0     # missing share that makes a column unusable
OUTLIER_WARNING_PCT = 5.0       # outlier share worth flagging as warning
HIGH_CORR_LEAKAGE = 0.95        # correlation pair treated as probable redundancy/leak
HIGH_CORR_INFO = 0.80           # correlation pair worth noting


def _rec(technique: str, alternatives: list[str], reason: str, risk: str) -> dict[str, Any]:
    return {
        "technique": technique,
        "alternatives": alternatives,
        "reason": reason,
        "risk": risk,
    }


def _issue(
    issue_id: str,
    severity: str,
    category: str,
    title: str,
    columns: list[str],
    detection_method: str,
    why_it_matters: str,
    recommendation: dict[str, Any],
    affected_count: int | None = None,
    affected_pct: float | None = None,
) -> dict[str, Any]:
    return {
        "id": issue_id,
        "severity": severity,
        "category": category,
        "title": title,
        "columns": columns,
        "affected_count": affected_count,
        "affected_pct": affected_pct,
        "detection_method": detection_method,
        "why_it_matters": why_it_matters,
        "recommendation": recommendation,
    }


def build_quality_report(profile: dict[str, Any]) -> dict[str, Any]:
    """
    Build the full quality report from a stored profile.
    Defensive against legacy profiles missing newer keys.
    Returns {"issues": [...], "summary": {...}} sorted critical → info.
    """
    issues: list[dict[str, Any]] = []

    if not profile or "error" in profile:
        return {
            "issues": [],
            "summary": {"critical": 0, "warning": 0, "info": 0, "available": False},
        }

    columns: dict[str, Any] = profile.get("columns", {})
    num_rows: int = int(profile.get("num_rows") or 0)

    # ── 1. Duplicate rows ───────────────────────────────────────────────────
    dup_rows = int(profile.get("duplicate_rows") or 0)
    if dup_rows > 0:
        pct = round(dup_rows / num_rows * 100, 2) if num_rows else None
        issues.append(
            _issue(
                "duplicates:rows",
                "critical",
                "duplicates",
                f"{dup_rows} duplicate rows detected",
                [],
                "Full-row equality check across all columns",
                "Duplicates inflate metrics and let the same example leak across "
                "train and test splits, producing over-optimistic scores.",
                _rec(
                    "Drop duplicate rows",
                    ["Keep duplicates if they are legitimately repeated measurements"],
                    "Identical rows add no information and bias validation.",
                    "Verify duplicates are not valid repeated observations before dropping.",
                ),
                affected_count=dup_rows,
                affected_pct=pct,
            )
        )

    # ── 2. Per-column checks ────────────────────────────────────────────────
    for col, stats in columns.items():
        semantic = stats.get("semantic_type", "text")
        null_count = int(stats.get("null_count") or 0)
        null_pct = float(stats.get("null_pct") or 0.0)

        # Missing values
        if null_count > 0:
            severity = "critical" if null_pct >= MISSING_CRITICAL_PCT else "warning"
            if semantic in ("numeric", "identifier"):
                skew = stats.get("skew")
                if skew is not None and abs(float(skew)) > SKEWED_THRESHOLD:
                    rec = _rec(
                        "Median imputation",
                        ["KNN imputation", "Iterative imputation", "Add missing-indicator column"],
                        "The distribution is skewed — median is robust to extreme values "
                        "where the mean would be dragged toward the tail.",
                        "Imputation narrows natural variance; an indicator column preserves that signal.",
                    )
                else:
                    rec = _rec(
                        "Mean imputation",
                        ["Median imputation", "KNN imputation"],
                        "Distribution is roughly symmetric, so the mean is a fair estimate "
                        "for absent values.",
                        "Mean imputation reduces variance and can weaken correlations.",
                    )
            elif semantic == "categorical":
                rec = _rec(
                    "Mode imputation or explicit 'Missing' category",
                    ["Model-based imputation"],
                    "For categories, filling with the most frequent value keeps the column usable; "
                    "a 'Missing' category preserves the absence as information.",
                    "Mode imputation over-represents the dominant class.",
                )
            elif semantic == "datetime":
                rec = _rec(
                    "Forward/backward fill",
                    ["Drop rows with missing timestamps"],
                    "Time-adjacent records are reasonable estimates for a missing timestamp.",
                    "Filling invents ordering that may not exist for sparse data.",
                )
            else:
                rec = _rec(
                    "Fill with 'Missing' placeholder",
                    ["Drop rows if the share is small"],
                    "Free-text absence is best kept visible rather than fabricated.",
                    "Placeholder tokens can fragment text statistics.",
                )
            issues.append(
                _issue(
                    f"missing:{col}",
                    severity,
                    "missing_values",
                    f"'{col}' contains {null_pct}% missing values ({null_count} of {num_rows})",
                    [col],
                    "Null scan per column",
                    (
                        "Most models cannot consume missing values natively; large gaps also "
                        "signal collection problems that can bias every downstream result."
                        if severity == "warning"
                        else "More than half the column is empty — the field is close to "
                        "unusable and can silently distort any model that consumes it."
                    ),
                    rec,
                    affected_count=null_count,
                    affected_pct=null_pct,
                )
            )

        # Constant / near-constant
        if stats.get("is_constant"):
            issues.append(
                _issue(
                    f"constant:{col}",
                    "info",
                    "constants",
                    f"'{col}' has a single value across all rows",
                    [col],
                    "Distinct-value count == 1",
                    "Constant columns carry zero predictive signal and can break "
                    "scaling or splitting logic.",
                    _rec(
                        "Drop the column",
                        ["Keep for reporting purposes only"],
                        "No variance means no information for a model to learn from.",
                        "None — removal is safe once documented.",
                    ),
                    affected_count=num_rows,
                )
            )
        elif stats.get("near_constant"):
            unique_count = int(stats.get("unique_count") or 0)
            issues.append(
                _issue(
                    f"near_constant:{col}",
                    "info",
                    "constants",
                    f"'{col}' is nearly constant ({unique_count} distinct values)",
                    [col],
                    "Unique-row ratio ≥ 98% with no missing values",
                    "Near-constant columns rarely help models and may be artifacts "
                    "(e.g., a flag set for one row).",
                    _rec(
                        "Review and likely drop",
                        ["Keep if rare values are business-critical events"],
                        "Signal-to-noise is extremely low.",
                        "Dropping loses the ability to detect those rare events.",
                    ),
                )
            )

        # High cardinality categoricals
        if stats.get("high_cardinality"):
            unique_count = int(stats.get("unique_count") or 0)
            issues.append(
                _issue(
                    f"high_cardinality:{col}",
                    "info",
                    "cardinality",
                    f"'{col}' has high cardinality ({unique_count} distinct values)",
                    [col],
                    f"Categorical/text column with > {100} distinct values",
                    "One-hot encoding such a column explodes dimensionality and "
                    "encourages overfitting on rare categories.",
                    _rec(
                        "Frequency or target encoding",
                        ["Group rare categories into 'Other'", "Hashing trick"],
                        "Compresses many rare levels while preserving frequency signal.",
                        "Target encoding must be fitted inside CV folds to avoid leakage.",
                    ),
                    affected_count=unique_count,
                )
            )

        # Outliers
        outliers = stats.get("outliers_count")
        if outliers:
            outliers = int(outliers)
            pct = round(outliers / num_rows * 100, 2) if num_rows else 0
            skew = stats.get("skew")
            skewed = skew is not None and abs(float(skew)) > SKEWED_THRESHOLD
            if pct >= OUTLIER_WARNING_PCT:
                severity = "warning"
            else:
                severity = "info"

            if skewed:
                rec = _rec(
                    "Log / power transform",
                    ["Cap (winsorize)", "Robust scaling", "Keep as-is"],
                    "The column is heavily skewed; a transform compresses the tail "
                    "instead of discarding legitimate large values.",
                    "Transforms change interpretability of coefficients.",
                )
            elif pct >= OUTLIER_WARNING_PCT:
                rec = _rec(
                    "Cap at IQR fences (winsorize)",
                    ["Remove flagged rows", "Robust scaling"],
                    "Capping limits influence of extremes without losing row count.",
                    "Capping distorts genuine extreme behavior — confirm with domain context.",
                )
            else:
                rec = _rec(
                    "Keep as-is",
                    ["Cap if confirmed data-entry errors"],
                    "Share of outliers is small; deleting real observations costs more "
                    "than it gains.",
                    "Outliers may be exactly the cases you need to predict.",
                )

            issues.append(
                _issue(
                    f"outliers:{col}",
                    severity,
                    "outliers",
                    f"'{col}' shows {outliers} potential outliers ({pct}%)",
                    [col],
                    "IQR fences (Q1 − 1.5·IQR, Q3 + 1.5·IQR)",
                    "Extreme values dominate distance-based and gradient-based models; "
                    "but some are legitimate rare events, never delete automatically.",
                    rec,
                    affected_count=outliers,
                    affected_pct=pct,
                )
            )

    # ── 3. Correlated feature pairs ─────────────────────────────────────────
    for pair in profile.get("correlations", []) or []:
        a, b, r = pair.get("a"), pair.get("b"), float(pair.get("r") or 0)
        severity = "warning" if abs(r) >= HIGH_CORR_LEAKAGE else "info"
        issues.append(
            _issue(
                f"correlation:{a}:{b}",
                severity,
                "correlations",
                f"'{a}' and '{b}' correlate at r = {r:.2f}",
                [a, b],
                "Pearson correlation between numeric columns",
                (
                    "At this level one column nearly duplicates the other; keeping both "
                    "inflates importance splits and destabilizes coefficients."
                    if severity == "warning"
                    else "Moderate multicollinearity — usually tolerable but worth noting "
                    "when interpreting feature importance."
                ),
                _rec(
                    f"Drop one of '{a}' / '{b}' (keep the cheaper or more complete)",
                    ["PCA / feature aggregation"],
                    "Redundant features add variance without adding signal.",
                    "Choosing which to drop needs domain judgment — the platform suggests, you decide.",
                ),
            )
        )

    # ── 4. Target leakage flags ─────────────────────────────────────────────
    for leak in profile.get("target_leakage", []) or []:
        leak_cols = leak.get("column")
        cols_list = leak_cols if isinstance(leak_cols, list) else [leak_cols]
        corr = leak.get("correlation")
        corr_txt = f" (r = {corr:.2f})" if isinstance(corr, (int, float)) else ""
        issues.append(
            _issue(
                f"leakage:{cols_list[0] if cols_list else 'unknown'}",
                "critical",
                "leakage",
                f"Possible target leakage in {', '.join(str(c) for c in cols_list)}{corr_txt}",
                [str(c) for c in cols_list],
                "Correlation-with-target threshold or identifier heuristics",
                "Features that encode the answer (directly or via IDs) produce models "
                "that score brilliantly offline and fail in production.",
                _rec(
                    "Exclude from model features",
                    ["Reconstruct the feature as it exists at prediction time"],
                    "Only features available at prediction time are legitimate inputs.",
                    "Excluding true predictors lowers accuracy — but honestly.",
                ),
            )
        )

    # ── 5. Class imbalance ──────────────────────────────────────────────────
    imbalance = profile.get("imbalance") or {}
    if imbalance.get("severity"):
        dist = imbalance.get("distribution", {})
        minority = min(dist.values()) if dist else None
        minority_pct = round(minority * 100, 2) if isinstance(minority, (int, float)) else None
        severe = imbalance["severity"] == "critical"
        issues.append(
            _issue(
                "imbalance:target",
                "critical" if severe else "info",
                "imbalance",
                f"Target classes are {'strongly' if severe else 'mildly'} imbalanced"
                + (f" (minority class ≈ {minority_pct}%)" if minority_pct is not None else ""),
                [],
                "Class-frequency distribution of the target column",
                (
                    "A model predicting the majority class everywhere already achieves high "
                    "accuracy — accuracy becomes meaningless and the minority class goes unseen."
                    if severe
                    else "Mild imbalance rarely blocks training but should shape metric choice."
                ),
                _rec(
                    "Use class weights or resampling (SMOTE / undersampling)",
                    ["Threshold tuning on predicted probabilities"],
                    "Balances the loss so minority errors are not ignored.",
                    "Resampling alters the data distribution; validate with F1/ROC-AUC, never accuracy alone.",
                ),
            )
        )

    issues.sort(key=lambda i: SEVERITY_ORDER.get(i["severity"], 3))

    summary = {
        "critical": sum(1 for i in issues if i["severity"] == "critical"),
        "warning": sum(1 for i in issues if i["severity"] == "warning"),
        "info": sum(1 for i in issues if i["severity"] == "info"),
        "available": True,
    }
    return {"issues": issues, "summary": summary}
