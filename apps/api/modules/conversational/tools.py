"""
AIDSE Platform — Analyst Tools (Phase 11)

Every number the AI Data Analyst can ever quote comes from one of these
tools, executed against the stored dataset profile or real training
artifacts. The LLM only CHOOSES tools and words the answer — it never
supplies values.

Contract:
    ToolSpec: name, description (for the LLM), parameters schema,
              handler(payload, args) -> dict of REAL computed results.
    handlers must be pure reads — no mutations, no arbitrary execution.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Tool implementations (profile-backed = deterministic + instant)
# ──────────────────────────────────────────────────────────────────────────────

def _dataset_summary(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    if not profile:
        return {
            "num_rows": None,
            "num_columns": None,
            "duplicate_rows": 0,
            "missing_cells": 0,
            "column_types": {},
            "target_candidate": None,
            "quality_critical": 0,
            "quality_warning": 0,
            "notes": ["No dataset is currently selected."],
        }
    cols = profile.get("columns", {})
    missing_cells = sum(int(s.get("null_count") or 0) for s in cols.values())
    semantic_counts: dict[str, int] = {}
    for s in cols.values():
        sem = s.get("semantic_type", "unknown")
        semantic_counts[sem] = semantic_counts.get(sem, 0) + 1
    quality = profile.get("quality_issues_summary", {})
    return {
        "num_rows": profile.get("num_rows"),
        "num_columns": profile.get("num_columns"),
        "duplicate_rows": profile.get("duplicate_rows"),
        "missing_cells": missing_cells,
        "column_types": semantic_counts,
        "target_candidate": (profile.get("target_candidate") or {}).get("column"),
        "quality_critical": quality.get("critical", 0),
        "quality_warning": quality.get("warning", 0),
        "notes": [
            "Counts come from the stored profile; sampled statistics are flagged "
            "when profiled_on_sample is true."
        ] if profile.get("profiled_on_sample") else [],
    }


def _column_statistics(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    column = args.get("column")
    cols = profile.get("columns", {})
    if not column or column not in cols:
        raise ValueError(f"Column '{column}' not found. Available: {list(cols)[:30]}")
    stats = cols[column]
    payload = {
        "column": column,
        "type": stats.get("type"),
        "semantic_type": stats.get("semantic_type"),
        "missing_pct": stats.get("null_pct"),
        "unique_values": stats.get("unique_count"),
        "is_constant": stats.get("is_constant"),
    }
    for key in ("min", "max", "mean", "median", "std", "skew", "outliers_count"):
        if key in stats:
            payload[key] = stats[key]
    if stats.get("top_values"):
        payload["most_frequent"] = stats["top_values"]
    return payload


def _missing_value_analysis(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    cols = profile.get("columns", {})
    per_column = {
        col: {"null_count": int(s.get("null_count") or 0), "null_pct": s.get("null_pct")}
        for col, s in cols.items()
        if int(s.get("null_count") or 0) > 0
    }
    per_column = dict(sorted(per_column.items(), key=lambda kv: kv[1]["null_count"], reverse=True))
    total_missing = sum(v["null_count"] for v in per_column.values())
    total_cells = int(profile.get("num_rows") or 0) * max(len(cols), 1)
    return {
        "columns_with_missing": len(per_column),
        "total_missing_cells": total_missing,
        "missing_share_of_all_cells_pct": round(total_missing / total_cells * 100, 2) if total_cells else 0,
        "per_column": per_column,
        "complete_columns": [c for c, s in cols.items() if int(s.get("null_count") or 0) == 0][:30],
    }


def _correlation_analysis(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    pairs = profile.get("correlations", []) or []
    target = args.get("target")
    result: list[dict[str, Any]] = [
        {"a": p["a"], "b": p["b"], "r": p["r"]} for p in pairs
    ]
    vs_target = None
    if target:
        vs_target = [
            p for p in result if target in (p["a"], p["b"])
        ]
    return {
        "strong_pairs": result[:10],
        "pairs_involving_target": vs_target,
        "threshold_note": "Only |r| >= 0.6 pairs are stored by profiling.",
    }


def _distribution_analysis(profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    column = args.get("column")
    cols = profile.get("columns", {})
    if not column or column not in cols:
        raise ValueError(f"Column '{column}' not found.")
    stats = cols[column]
    hist = stats.get("histogram")
    payload: dict[str, Any] = {
        "column": column,
        "semantic_type": stats.get("semantic_type"),
        "skew": stats.get("skew"),
        "shape_note": (
            "right-skewed (long tail toward high values)" if isinstance(stats.get("skew"), (int, float)) and stats["skew"] > 1
            else "left-skewed (long tail toward low values)" if isinstance(stats.get("skew"), (int, float)) and stats["skew"] < -1
            else "roughly symmetric"
        ),
    }
    if hist:
        payload["histogram"] = hist
    if stats.get("top_values"):
        payload["category_counts"] = stats["top_values"]
    if not hist and not stats.get("top_values"):
        raise ValueError(
            f"No distribution data stored for '{column}'. "
            "Distribution histograms cover numeric columns; categorical counts cover categories."
        )
    return payload


def _data_quality_overview(_profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    report = args.get("_quality_report") or {}
    issues = report.get("issues", [])
    summary = report.get("summary", {})
    return {
        "summary": {k: summary.get(k) for k in ("critical", "warning", "info")},
        "issues": [
            {
                "severity": i["severity"],
                "title": i["title"],
                "recommendation": i["recommendation"]["technique"],
            }
            for i in issues[:15]
        ],
    }


def _preprocessing_recommendation(_profile: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    plan = args.get("_recommendation_plan") or {}
    steps = plan.get("steps", [])
    return {
        "narrative": plan.get("narrative"),
        "steps": [
            {
                "order": s["order"],
                "action": s["action"],
                "column": s["column"],
                "why": s["rationale"],
            }
            for s in steps
        ],
        "note": "Steps require user approval before anything runs.",
    }


# ── Model-aware tools (real artifacts from training) ─────────────────────────

def _model_metrics(args: dict[str, Any]) -> dict[str, Any]:
    evaluation = args.get("_evaluation") or {}
    return {
        "status": evaluation.get("status"),
        "problem_type": evaluation.get("problem_type"),
        "primary_metric": evaluation.get("primary_metric"),
        "metrics": [
            {"metric": m["metric"], "value": m["value"], "interpretation": m["interpretation"]}
            for m in evaluation.get("metrics", [])
        ],
        "best_algorithm": (
            evaluation["trial_comparisons"][0]["algorithm"]
            if evaluation.get("trial_comparisons") else None
        ),
    }


def _feature_importance(args: dict[str, Any]) -> dict[str, Any]:
    explanation = args.get("_global_explanation") or {}
    importances = explanation.get("feature_importances") or {}
    if not importances:
        raise ValueError(
            "No feature importance available yet. Generate a global explanation "
            "for the best trial first (ML Lab → Explain)."
        )
    return {
        "method": explanation.get("explanation_method"),
        "top_features": importances,
        "insight": explanation.get("insight"),
    }


def _evaluation_results(args: dict[str, Any]) -> dict[str, Any]:
    evaluation = args.get("_evaluation") or {}
    cm = evaluation.get("confusion_matrix")
    return {
        "primary_metric": evaluation.get("primary_metric"),
        "metrics": [
            {"metric": m["metric"], "value": m["value"], "interpretation": m["interpretation"]}
            for m in evaluation.get("metrics", [])
        ],
        "confusion_matrix": cm,
        "reading_guide": evaluation.get("confusion_matrix_reading_guide"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────

class ToolSpec:
    def __init__(self, name: str, description: str, parameters: dict[str, Any],
                 handler: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
                 requires_profile: bool = True):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.requires_profile = requires_profile

    def execute(self, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        return self.handler(payload, args)


TOOLS: dict[str, ToolSpec] = {
    t.name: t for t in [
        ToolSpec(
            "dataset_summary",
            "Overall dataset shape and health: rows, columns, duplicate rows, "
            "missing cells, column type mix, target candidate suggestion.",
            {"type": "object", "properties": {}},
            _dataset_summary,
        ),
        ToolSpec(
            "column_statistics",
            "Detailed statistics for ONE column: type, missing %, unique values, "
            "and min/max/mean/median/std/skew for numeric or top categories otherwise.",
            {"type": "object", "properties": {"column": {"type": "string"}}, "required": ["column"]},
            _column_statistics,
        ),
        ToolSpec(
            "missing_value_analysis",
            "Missing-value breakdown across all columns: which columns have nulls, "
            "how many, ranked worst-first.",
            {"type": "object", "properties": {}},
            _missing_value_analysis,
        ),
        ToolSpec(
            "correlation_analysis",
            "Strongest feature correlations. Optionally filter to pairs involving "
            "one target/feature via 'target'.",
            {"type": "object", "properties": {"target": {"type": "string"}}},
            _correlation_analysis,
        ),
        ToolSpec(
            "distribution_analysis",
            "Distribution of ONE column: histogram bins for numerics or category "
            "counts, plus skew interpretation.",
            {"type": "object", "properties": {"column": {"type": "string"}}, "required": ["column"]},
            _distribution_analysis,
        ),
        ToolSpec(
            "model_metrics",
            "Metrics of the latest/best trained model with plain-language readings.",
            {"type": "object", "properties": {}},
            lambda p, a: _model_metrics(a),
            requires_profile=False,
        ),
        ToolSpec(
            "feature_importance",
            "Which features most influence the trained model's predictions.",
            {"type": "object", "properties": {}},
            lambda p, a: _feature_importance(a),
            requires_profile=False,
        ),
        ToolSpec(
            "evaluation_results",
            "Full evaluation of the best model including confusion matrix.",
            {"type": "object", "properties": {}},
            lambda p, a: _evaluation_results(a),
            requires_profile=False,
        ),
        ToolSpec(
            "preprocessing_recommendation",
            "The rule-engine's approved-pending preprocessing plan for this dataset.",
            {"type": "object", "properties": {}},
            _preprocessing_recommendation,
        ),
    ]
}


def execute_tool(name: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Run a registered tool. Raises ValueError with user-facing messages."""
    tool = TOOLS.get(name)
    if not tool:
        raise ValueError(f"Unknown tool '{name}'.")
    return tool.execute(payload, args)
