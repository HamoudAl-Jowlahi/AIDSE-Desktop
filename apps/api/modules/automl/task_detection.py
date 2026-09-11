"""
AIDSE Platform — ML Task Detection (Phase 7)

Inspects a stored dataset profile plus the chosen target column and decides:

    classification | regression | unsupervised

with an explicit honesty rule: when the evidence is ambiguous (e.g. a numeric
column with few distinct values), the detector says so and asks the user to
confirm instead of guessing their business objective.

Also recommends suitable metrics per task and per class balance, and the
focused default model set (Phase 8).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

AMBIGUOUS_UNIQUE_MAX = 20       # numeric targets within this range need confirmation
BINARY_UNIQUE = 2
IMBALANCE_INFO_PCT = 20.0
IMBALANCE_CRITICAL_PCT = 5.0
SKEWED_TARGET_THRESHOLD = 1.0   # consistent with the Data Quality engine's definition


FOCUSED_MODELS: dict[str, list[dict[str, str]]] = {
    "classification": [
        {"id": "logistic_regression", "name": "Logistic Regression",
         "why": "Fast, interpretable baseline; coefficients read as feature effects."},
        {"id": "random_forest", "name": "Random Forest",
         "why": "Robust on tabular data; little tuning needed; handles non-linearities."},
        {"id": "xgboost", "name": "XGBoost",
         "why": "Usually the strongest tabular performer; handles missing values natively."},
        {"id": "svm", "name": "SVM (RBF)",
         "why": "Strong on small-to-medium datasets with clear margins."},
    ],
    "regression": [
        {"id": "linear_regression", "name": "Linear Regression",
         "why": "Interpretable baseline; shows linear relationships directly."},
        {"id": "random_forest", "name": "Random Forest Regressor",
         "why": "Captures non-linear patterns without feature scaling."},
        {"id": "xgboost", "name": "XGBoost Regressor",
         "why": "High accuracy on structured data; robust to outliers in features."},
    ],
}

METRIC_EXPLANATIONS: dict[str, str] = {
    "accuracy": "Share of all predictions that were correct.",
    "f1_macro": "Balance of precision and recall, averaged across classes — fair when classes differ in size.",
    "recall": "Of the actual positive cases, the percentage the model caught.",
    "precision": "When the model predicts positive, how often it is right.",
    "roc_auc": "Ability to rank a random positive above a random negative (0.5 = random guessing).",
    "r2": "Percentage of the target's variance the model explains (1.0 = perfect).",
    "rmse": "Typical size of prediction error, in target units — punishes large mistakes.",
    "mae": "Average absolute error, in target units — easy to read, forgiving of outliers.",
}


def suggest_targets(profile: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """
    Rank plausible target columns when the user hasn't chosen one.

    Scoring (higher first):
      100  name match (target/label/y/class/outcome)
      ~70  categorical/boolean with a small distinct set (classification label)
      ~65  binary numeric column
      ~30  plain numeric column (regression — weak guess)

    Penalties: missing values and near-constant columns drop fast.
    Identifiers, constants and hopeless (>60% missing) columns are excluded.
    """
    NAME_MATCHES = ("target", "label", "y", "class", "outcome")
    candidates: list[tuple[float, dict[str, Any]]] = []

    for col, s in (profile.get("columns") or {}).items():
        semantic = s.get("semantic_type", "text")
        unique_count = int(s.get("unique_count") or 0)
        null_pct = float(s.get("null_pct") or 0.0)

        if semantic == "identifier" or s.get("is_constant") or null_pct >= 60:
            continue

        base: float | None = None
        task = "classification"
        reason = ""

        lowered = str(col).strip().lower()
        if lowered in NAME_MATCHES:
            base, reason = 100.0, "Column name explicitly suggests it is the target."
        elif semantic == "categorical" or (
            semantic == "boolean"
        ):
            if 2 <= unique_count <= AMBIGUOUS_UNIQUE_MAX:
                base = 70.0 - null_pct * 0.5
                task = "classification"
                reason = f"{unique_count} distinct categories look like class labels."
        elif semantic == "numeric":
            if unique_count <= BINARY_UNIQUE:
                base = 65.0 - null_pct * 0.5
                reason = f"Numeric with only {unique_count} values — likely a binary label."
            elif unique_count > AMBIGUOUS_UNIQUE_MAX:
                base = 30.0 - null_pct * 0.5
                task = "regression"
                reason = "Continuous numeric column; a regression target is plausible but unconfirmed."

        if base is None:
            continue

        confidence = "high" if base >= 95 else "medium" if base >= 60 else "low"
        candidates.append((base, {
            "column": str(col),
            "task_type": task,
            "confidence": confidence,
            "reason": reason,
        }))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    ranked = [c for _, c in candidates[:limit]]
    for i, c in enumerate(ranked, start=1):
        c["rank"] = i
    return ranked


def detect_task(profile: dict[str, Any], target_column: str | None) -> dict[str, Any]:
    """
    Decide the ML task from the stored profile.

    Returns:
      {
        target_column, task_type, confidence, needs_confirmation,
        question (when ambiguous), notes[], class_balance,
        recommended_metrics: [{metric, primary, explanation}],
        recommended_models: [...]
      }
    """
    result: dict[str, Any] = {
        "target_column": target_column,
        "task_type": None,
        "confidence": None,
        "needs_confirmation": False,
        "question": None,
        "notes": [],
        "class_balance": None,
        "recommended_metrics": [],
        "recommended_models": [],
    }

    columns: dict[str, Any] = profile.get("columns", {})

    # ── No target chosen → suggest candidate(s), offer unsupervised ────────
    if not target_column:
        candidate = (profile.get("target_candidate") or {}).get("column")
        ranked = suggest_targets(profile)
        result["task_type"] = "unsupervised"
        result["confidence"] = "none"
        result["suggested_targets"] = ranked
        result["notes"].append(
            "No target selected — supervised learning needs one. "
            + (f"The system suggests '{candidate}' based on the profile; confirm or pick another."
               if candidate else
               "Pick the column you want to predict.")
        )
        if candidate:
            result["suggested_target"] = candidate
        return result

    if target_column not in columns:
        result["notes"].append(f"Column '{target_column}' was not found in this dataset version.")
        return result

    stats = columns[target_column]
    semantic = stats.get("semantic_type", "text")
    unique_count = int(stats.get("unique_count") or 0)
    skew = stats.get("skew")

    # ── Identifier targets are almost never real objectives ─────────────────
    if semantic == "identifier":
        result["notes"].append(
            f"'{target_column}' looks like an identifier (unique per row). "
            "Predicting it is usually meaningless — double-check your choice."
        )

    # ── Classification branch ────────────────────────────────────────────────
    if semantic in ("categorical", "boolean") or (
        semantic == "text" and unique_count <= AMBIGUOUS_UNIQUE_MAX
    ):
        _finish_classification(result, stats, unique_count)
        return result

    if semantic == "numeric":
        if unique_count <= BINARY_UNIQUE:
            result.update(
                task_type="classification",
                confidence="medium",
                needs_confirmation=True,
                question=(
                    f"'{target_column}' is numeric but has only {unique_count} distinct values "
                    "(e.g. 0/1). Treat it as binary classification?"
                ),
            )
            _finish_classification(result, stats, unique_count, override_confidence=False)
            return result

        if unique_count <= AMBIGUOUS_UNIQUE_MAX:
            # Ambiguity: could be ordinal codes (classification) or a quantity (regression)
            result.update(
                task_type="classification",
                confidence="low",
                needs_confirmation=True,
                question=(
                    f"'{target_column}' is numeric with {unique_count} distinct values. "
                    "Are these category codes (classification) or quantities (regression)?"
                ),
            )
            _finish_classification(result, stats, unique_count, override_confidence=False)
            result["alternative_task"] = "regression"
            return result

        # ── Regression branch ────────────────────────────────────────────────
        result.update(task_type="regression", confidence="high")
        if isinstance(skew, (int, float)) and abs(skew) > SKEWED_TARGET_THRESHOLD:
            result["notes"].append(
                "The target is heavily skewed — consider a log transform of the target "
                "or a Huber-loss model so extreme values do not dominate training."
            )
        result["recommended_metrics"] = [
            {"metric": "r2", "primary": True, "explanation": METRIC_EXPLANATIONS["r2"]},
            {"metric": "rmse", "primary": False, "explanation": METRIC_EXPLANATIONS["rmse"]},
            {"metric": "mae", "primary": False, "explanation": METRIC_EXPLANATIONS["mae"]},
        ]
        result["recommended_models"] = FOCUSED_MODELS["regression"]
        return result

    # Free text fallback → treat like classification attempt
    _finish_classification(result, stats, unique_count)
    result["notes"].insert(0, "Target is free text — verify categories are meaningful before training.")
    return result


def _finish_classification(
    result: dict[str, Any],
    stats: dict[str, Any],
    unique_count: int,
    override_confidence: bool = True,
) -> None:
    result["task_type"] = "classification"
    if override_confidence:
        result["confidence"] = "high" if unique_count > 0 else "low"

    # Class balance drives metric advice
    profile_imbalance = stats  # per-column stats may carry nothing; use top-level when available
    minority_pct = _minority_share(stats)

    if minority_pct is not None and minority_pct < IMBALANCE_CRITICAL_PCT:
        result["class_balance"] = {"status": "critical", "minority_pct": minority_pct}
        result["notes"].append(
            f"Minority class ≈ {minority_pct}% — accuracy will look good even for a useless model. "
            "Optimize F1 or ROC-AUC instead."
        )
    elif minority_pct is not None and minority_pct < IMBALANCE_INFO_PCT:
        result["class_balance"] = {"status": "imbalanced", "minority_pct": minority_pct}
        result["notes"].append(
            f"Minority class ≈ {minority_pct}% — prefer F1/ROC-AUC over raw accuracy."
        )
    else:
        result["class_balance"] = {"status": "balanced"}

    result["recommended_metrics"] = [
        {"metric": "f1_macro", "primary": True, "explanation": METRIC_EXPLANATIONS["f1_macro"]},
        {"metric": "accuracy", "primary": False, "explanation": METRIC_EXPLANATIONS["accuracy"]},
        {"metric": "roc_auc", "primary": False, "explanation": METRIC_EXPLANATIONS["roc_auc"]},
    ]
    result["recommended_models"] = FOCUSED_MODELS["classification"]


def _minority_share(stats: dict[str, Any]) -> float | None:
    """Minority-class share from top_values when the column is low-cardinality."""
    top = stats.get("top_values")
    if not top:
        return None
    counts = sorted(top.values(), reverse=True)
    total = sum(counts)
    if total <= 0 or len(counts) < 2:
        return None
    return round(counts[-1] / total * 100, 2)
