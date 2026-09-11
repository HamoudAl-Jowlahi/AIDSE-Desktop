"""
AIDSE Platform — Model Evaluation Builder (Phase 9)

Turns stored trial metrics into an explained evaluation report:

    number  →  plain-language meaning  →  sentence about THIS model

Example rendering produced here:
    recall = 0.91 → "Recall: of the actual positive cases, the model caught 91%."

The confusion matrix and per-class breakdown recorded during training are
surfaced verbatim; nothing is recomputed at read time.
"""
from __future__ import annotations

from typing import Any

from apps.api.modules.automl.task_detection import METRIC_EXPLANATIONS

PRIMARY_METRICS = {
    "classification": ["f1_macro", "accuracy", "roc_auc", "precision", "recall"],
    "regression": ["r2", "rmse", "mae", "mse"],
}

HIGHER_IS_BETTER = {
    "accuracy": True, "f1_macro": True, "roc_auc": True,
    "precision": True, "recall": True, "r2": True,
    "rmse": False, "mae": False, "mse": False,
}


def _pct(v: float) -> str:
    pct = round(float(v) * 100, 1)
    if pct == int(pct):
        pct = int(pct)
    return f"{pct}%"


def interpret(metric: str, value: float) -> str:
    """Plain-language sentence about what THIS value means for THIS model."""
    v = float(value)
    if metric == "accuracy":
        return f"{_pct(v)} of all predictions were correct."
    if metric == "recall":
        return f"The model detected {_pct(v)} of the actual positive cases."
    if metric == "precision":
        return f"When the model predicts positive, it is right {_pct(v)} of the time."
    if metric == "f1_macro":
        return (
            f"Balanced precision/recall across classes is {_pct(v)} — "
            + ("strong overall." if v >= 0.75 else "moderate; check per-class results." if v >= 0.5 else "weak.")
        )
    if metric == "roc_auc":
        return (
            f"A random positive outranks a random negative {_pct(v)} of the time "
            + ("(0.5 would be coin-flip)." if v < 0.65 else "")
        ).strip()
    if metric == "r2":
        return f"The model explains {_pct(max(v, 0))} of the target's variance."
    if metric == "rmse":
        return f"Typical prediction error is about {v:,.3g} units — large misses weigh heaviest."
    if metric == "mae":
        return f"On average, predictions miss by {v:,.3g} units."
    if metric == "mse":
        return f"Mean squared error in squared units ({v:,.4g}); compare between models only."
    return ""


def build_evaluation(experiment) -> dict[str, Any]:
    """
    Build the Phase 9 evaluation payload for a completed experiment.
    `experiment` must have trials eagerly loaded.
    """
    problem_type: str = experiment.problem_type
    trials = list(experiment.trials or [])
    lower_better = experiment.primary_metric in ("rmse", "mae", "mse")

    def rank_key(t):
        s = t.primary_metric_score
        if s is None:
            return float("inf") if lower_better else float("-inf")
        return s

    ranked = sorted(
        [t for t in trials if t.status == "completed"],
        key=rank_key,
        reverse=not lower_better,
    )

    def trial_metrics(t) -> list[dict[str, Any]]:
        out = []
        raw = t.metrics or {}
        order = PRIMARY_METRICS.get(problem_type, list(raw.keys()))
        for name in order + [k for k in raw if k not in order]:
            value = raw.get(name)
            if not isinstance(value, (int, float)):
                continue  # skip nested structures (confusion_matrix etc.)
            entry: dict[str, Any] = {
                "metric": name,
                "value": round(float(value), 6),
                "explanation": METRIC_EXPLANATIONS.get(name, ""),
                "interpretation": interpret(name, float(value)),
                "higher_is_better": HIGHER_IS_BETTER.get(name, True),
                "is_primary": name == experiment.primary_metric,
            }
            out.append(entry)
        return out

    best = ranked[0] if ranked else None

    response: dict[str, Any] = {
        "experiment_id": str(experiment.id),
        "problem_type": problem_type,
        "primary_metric": experiment.primary_metric,
        "target_column": experiment.target_column,
        "status": experiment.status,
        "trials_evaluated": len(ranked),
        "metrics": trial_metrics(best) if best else [],
        "confusion_matrix": None,
        "per_class": None,
        "trial_comparisons": [
            {
                "trial_id": str(t.id),
                "algorithm": t.algorithm_name,
                "primary_score": t.primary_metric_score,
                "is_best": t.is_best,
            }
            for t in ranked
        ],
    }

    if best and isinstance(best.metrics, dict):
        cm = best.metrics.get("confusion_matrix")
        if cm:
            response["confusion_matrix"] = cm
        pc = best.metrics.get("per_class")
        if pc:
            response["per_class"] = [
                {"class_name": label, **stats} for label, stats in pc.items()
            ]

    # Reading guide for the confusion matrix when present
    if response["confusion_matrix"]:
        labels = response["confusion_matrix"]["labels"]
        if len(labels) == 2:
            neg, pos = labels
            response["confusion_matrix_reading_guide"] = (
                f"Rows are the true class, columns the predicted class. "
                f"Top-left = correct '{neg}', bottom-right = correct '{pos}'. "
                f"Off-diagonal cells are mistakes — bottom-left are missed '{pos}' cases."
            )
        else:
            response["confusion_matrix_reading_guide"] = (
                "Rows are the true class, columns the predicted class. "
                "The diagonal holds correct predictions; everything off it is a mistake."
            )

    return response
