"""
AIDSE Platform — AI Recommendation Engine (Phase 6)

Hybrid architecture:

    ┌──────────────────────────┐
    │ Rule/Statistical engine   │  deterministic; inspects the stored
    │ (this module, build_plan) │  profile and emits an ordered,
    └────────────┬─────────────┘  EXECUTABLE preprocessing plan where
                 │                every step maps to a real transform.py
                 ▼                action with params.
    ┌──────────────────────────┐
    │ LLM explanation layer     │  narrates what the rules decided and
    │ (explain_plan)            │  why, in plain language. It NEVER
    └───────────────────────────┘  computes statistics or invents steps.

Safety rules:
- The plan is advisory. Nothing runs until the user queues and applies it.
- Steps reference only transform.py actions, so a recommended plan can be
  dry-run through preview_transformations() before approval.
- The LLM receives aggregate profile statistics only (never dataset rows),
  and its output is narrative text — never executable steps.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from apps.api.core.config import get_settings

logger = logging.getLogger(__name__)

# Column missing-share above which dropping beats imputing
DROP_MISSING_PCT = 60.0
LOW_CARDINALITY_ONE_HOT = 15
OUTLIER_TREAT_SHARE = 1.0  # % of rows flagged before treatment is suggested
MAX_PLAN_STEPS = 25


# ──────────────────────────────────────────────────────────────────────────────
# Rules layer
# ──────────────────────────────────────────────────────────────────────────────

def _step(
    order: int,
    action: str,
    column: str | None,
    problem: str,
    rationale: str,
    expected_effect: str,
    alternatives: list[str] | None = None,
    confidence: str = "medium",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "order": order,
        "action": action,          # always a real transform.py action
        "column": column,
        "params": params or {},
        "problem": problem,
        "rationale": rationale,
        "expected_effect": expected_effect,
        "alternatives": alternatives or [],
        "confidence": confidence,  # high | medium | low
    }


def build_plan(profile: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministic rules → ordered, executable preprocessing plan.

    Ordering rationale:
      type fixes → missing values → outliers → structure drops →
      encoding → scaling (each stage assumes the previous one's output).
    """
    columns: dict[str, Any] = profile.get("columns", {})
    num_rows_total = int(profile.get("num_rows") or 0)
    target_candidate = (profile.get("target_candidate") or {}).get("column")
    imbalance = profile.get("imbalance") or {}

    stages: dict[str, list[dict[str, Any]]] = {
        "convert": [], "missing": [], "outliers": [],
        "structure": [], "encoding": [], "scaling": [],
    }

    for col, stats in columns.items():
        semantic = stats.get("semantic_type", "text")
        null_pct = float(stats.get("null_pct") or 0.0)
        unique_count = int(stats.get("unique_count") or 0)
        outliers_count = int(stats.get("outliers_count") or 0)
        skew = stats.get("skew")
        is_target = target_candidate == col

        # 0. Type fixes — numeric-looking strings block every later step
        if semantic == "text" and null_pct < DROP_MISSING_PCT:
            stages["convert"].append(
                _step(
                    0, "convert_type", col,
                    problem=f"'{col}' is stored as free text",
                    rationale="Converting to numeric makes the column usable by models "
                              "and unlocks correct imputation/scaling downstream.",
                    expected_effect="Numeric dtype; unparseable values become NaN and are handled next.",
                    confidence="low",
                    params={"to": "numeric"},
                )
            )

        # 1a. Hopeless columns — drop instead of impute
        if null_pct >= DROP_MISSING_PCT:
            stages["structure"].append(
                _step(
                    0, "drop_column", col,
                    problem=f"'{col}' is {null_pct}% empty",
                    rationale="Beyond this threshold imputation would fabricate most of the column.",
                    expected_effect="Fewer noise sources; no fabricated data.",
                    alternatives=["Fill with a constant 'Missing' flag if absence itself matters"],
                    confidence="high",
                )
            )
            continue  # no point treating further

        # 1b. Constant columns carry zero signal
        if stats.get("is_constant"):
            stages["structure"].append(
                _step(
                    0, "drop_column", col,
                    problem=f"'{col}' has a single value in all rows",
                    rationale="Constant columns cannot help a model discriminate anything.",
                    expected_effect="Leaner feature space with zero information loss.",
                    confidence="high",
                )
            )
            continue

        # 2. Missing-value handling (skip identifiers — they are excluded later)
        if null_pct > 0:
            if semantic == "numeric":
                skewed = isinstance(skew, (int, float)) and abs(skew) > 1.0
                stages["missing"].append(
                    _step(
                        0, "fillna_median" if skewed else "fillna_mean", col,
                        problem=f"{null_pct}% of '{col}' is missing"
                                + (" with a skewed distribution" if skewed else ""),
                        rationale="Median resists extreme values on skewed data."
                                  if skewed else
                                  "The distribution is roughly symmetric so the mean is a fair estimate.",
                        expected_effect="Complete column without dropping rows.",
                        alternatives=["KNN imputation"] if skewed else ["Median imputation", "KNN imputation"],
                        confidence="high" if skewed else "medium",
                    )
                )
            elif semantic in ("categorical", "boolean"):
                stages["missing"].append(
                    _step(
                        0, "fillna_mode", col,
                        problem=f"{null_pct}% of categorical '{col}' is missing",
                        rationale="Most-frequent fill keeps the category usable for encoding.",
                        expected_effect="No NaNs remain to break one-hot/label encoding.",
                        alternatives=["Explicit 'Missing' category via constant fill"],
                        confidence="high",
                    )
                )

        # 3. Outlier treatment (only meaningful once imputation has run)
        if outliers_count > 0 and num_rows_total > 0:
            share_pct = round(outliers_count / max(num_rows_total - int(stats.get("null_count") or 0), 1) * 100, 2)
            if share_pct >= OUTLIER_TREAT_SHARE:
                heavy_skew = isinstance(skew, (int, float)) and abs(skew) > 1.5
                if heavy_skew:
                    stages["outliers"].append(
                        _step(
                            0, "log_transform", col,
                            problem=f"'{col}' shows {share_pct}% outliers on a strongly skewed tail",
                            rationale="Compresses the tail multiplicatively while keeping every row.",
                            expected_effect="Symmetric-ish distribution; friendlier for linear models.",
                            alternatives=["Winsorize at p1/p99", "Keep as-is with robust scaling"],
                            confidence="medium",
                        )
                    )
                elif not stats.get("is_constant"):
                    stages["outliers"].append(
                        _step(
                            0, "winsorize", col,
                            problem=f"'{col}' shows {share_pct}% IQR outliers",
                            rationale="Capping limits leverage of extremes without discarding rows.",
                            expected_effect="Bounded range [p1, p99]; mean/std stabilize.",
                            alternatives=["Cap at IQR fences", "Robust scaling only"],
                            confidence="medium",
                            params={"lower_pct": 0.01, "upper_pct": 0.99},
                        )
                    )

        # 4. Encoding for categoricals (after imputation)
        if semantic == "categorical" and not is_target:
            if unique_count <= LOW_CARDINALITY_ONE_HOT:
                stages["encoding"].append(
                    _step(
                        0, "one_hot_encode", col,
                        problem=f"Categorical '{col}' has {unique_count} distinct values",
                        rationale="Low cardinality one-hot keeps categories fully separable.",
                        expected_effect=f"{unique_count} indicator columns; no ordinal assumption.",
                        alternatives=["Label encode if the model handles splits natively (trees)"],
                        confidence="high",
                    )
                )
            elif stats.get("high_cardinality"):
                stages["encoding"].append(
                    _step(
                        0, "frequency_encode", col,
                        problem=f"'{col}' is high-cardinality ({unique_count} distinct values)",
                        rationale="Frequency encoding compresses many levels into one numeric signal.",
                        expected_effect="Single numeric column; tree models split on frequency mass.",
                        alternatives=["Target encoding (must stay inside CV folds)", "Hashing"],
                        confidence="medium",
                    )
                )

        # 5. Scaling numerics last (post-outlier-treatment)
        if semantic == "numeric":
            had_outliers = outliers_count > 0 and any(
                s["action"] in ("log_transform", "winsorize")
                for s in stages["outliers"] if s["column"] == col
            )
            if had_outliers:
                stages["scaling"].append(
                    _step(
                        0, "robust_scale", col,
                        problem=f"'{col}' needed outlier treatment above",
                        rationale="Median/IQR scaling stays stable even after mild residual spread.",
                        expected_effect="Comparable feature magnitudes, insensitive to remaining tails.",
                        confidence="medium",
                    )
                )

    ordered: list[dict[str, Any]] = []
    for stage_name in ("convert", "missing", "outliers", "structure", "encoding", "scaling"):
        ordered.extend(stages[stage_name])
    for i, step in enumerate(ordered[:MAX_PLAN_STEPS], start=1):
        step["order"] = i

    notes: list[str] = []
    if imbalance.get("severity"):
        notes.append(imbalance["warning"])
    identifier_like = [c for c, s in columns.items() if s.get("semantic_type") == "identifier"]
    if identifier_like:
        notes.append(
            f"Identifier-like columns ({', '.join(identifier_like)}) were left untouched — "
            "exclude them from model features at training time rather than deleting them."
        )
    if len(ordered) > MAX_PLAN_STEPS:
        notes.append(f"Plan truncated to the {MAX_PLAN_STEPS} highest-impact steps.")

    return {
        "steps": ordered,
        "notes": notes,
        "stats_summary": {
            "total_steps": len(ordered),
            "columns_affected": len({s["column"] for s in ordered if s["column"]}),
            "target_column_hint": target_candidate,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# LLM explanation layer
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a senior data scientist writing short explanations for a preprocessing "
    "plan that a rule engine produced. You receive aggregate statistics ONLY — never "
    "raw rows. Explain in plain language (max 180 words), structured as: what the data "
    "struggles with, why this plan order makes sense, and what to watch out for. "
    "Do NOT invent statistics beyond what you are given. Do NOT add or remove steps."
)


def _llm_configured(settings) -> bool:
    return settings.LLM_PROVIDER in ("openai", "anthropic") and bool(settings.LLM_API_KEY)


def explain_with_llm(plan_steps: list[dict[str, Any]], profile_summary: dict[str, Any]) -> str | None:
    """
    Ask the configured provider to narrate the plan.
    Returns None when unconfigured or on ANY failure — caller falls back
    to deterministic templates. Never raises.
    """
    settings = get_settings()
    if not _llm_configured(settings):
        return None

    compact = [
        {
            "order": s["order"], "action": s["action"], "column": s["column"],
            "problem": s["problem"], "why": s["rationale"],
        }
        for s in plan_steps
    ]
    user_content = (
        f"Dataset summary: {json.dumps(profile_summary)}\n"
        f"Plan: {json.dumps(compact)}\n"
        "Explain this plan briefly for a non-expert."
    )

    try:
        import httpx

        if settings.LLM_PROVIDER == "openai":
            url = (settings.LLM_BASE_URL or "https://api.openai.com/v1") + "/chat/completions"
            model = settings.LLM_MODEL or "gpt-4o-mini"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": 400,
                "temperature": 0.3,
            }
            headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
        else:  # anthropic
            url = settings.LLM_BASE_URL or "https://api.anthropic.com/v1/messages"
            model = settings.LLM_MODEL or "claude-3-5-haiku-latest"
            payload = {
                "model": model,
                "max_tokens": 400,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            }
            headers = {"x-api-key": settings.LLM_API_KEY, "anthropic-version": "2023-06-01"}

        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        if settings.LLM_PROVIDER == "openai":
            return str(data["choices"][0]["message"]["content"]).strip()
        return str(data["content"][0]["text"]).strip()
    except Exception as exc:
        logger.warning("LLM explanation unavailable (%s); using template narration.", exc)
        return None


def explain_with_template(plan_steps: list[dict[str, Any]], profile: dict[str, Any]) -> str:
    """Deterministic plain-language narration used whenever the LLM layer is off."""
    if not plan_steps:
        return (
            "This dataset looks ready as-is: no missing values, duplicates, constants or "
            "outlier problems were detected. You can proceed to ML training."
        )

    by_stage: dict[str, list[str]] = {}
    for s in plan_steps:
        key = {
            "convert_type": "type conversion",
            "fillna_mean": "imputation", "fillna_median": "imputation",
            "fillna_mode": "imputation",
            "log_transform": "outlier treatment", "winsorize": "outlier treatment",
            "drop_column": "cleanup",
            "one_hot_encode": "categorical encoding", "frequency_encode": "categorical encoding",
            "robust_scale": "scaling",
        }.get(s["action"], s["action"])
        by_stage.setdefault(key, []).append(s["column"] or "")

    parts: list[str] = []
    n_cols = profile.get("num_columns", "?")
    n_rows = profile.get("num_rows", "?")

    intro = f"This plan prepares your dataset of {n_rows} rows × {n_cols} columns in {len(plan_steps)} approved-by-you steps. "
    parts.append(intro)

    if "imputation" in by_stage:
        cols = ", ".join(c for c in by_stage["imputation"] if c)
        parts.append(f"Missing values appear in {cols}; they are filled first so later steps see complete data.")
    if "outlier treatment" in by_stage:
        cols = ", ".join(c for c in by_stage["outlier treatment"] if c)
        parts.append(f"Extreme values in {cols} are tamed with transforms or percentile caps instead of deleting real observations.")
    if "cleanup" in by_stage:
        cols = ", ".join(c for c in by_stage["cleanup"] if c)
        parts.append(f"Columns carrying no usable signal ({cols}) are removed.")
    if "categorical encoding" in by_stage:
        cols = ", ".join(c for c in by_stage["categorical encoding"] if c)
        parts.append(f"Category columns ({cols}) are converted to numbers the models can consume.")
    if "scaling" in by_stage:
        cols = ", ".join(c for c in by_stage["scaling"] if c)
        parts.append(f"Finally {cols} are scaled so distance-based models treat features fairly.")

    parts.append("Nothing is applied until you review and approve — each step can be previewed, reordered or dropped first.")
    return " ".join(parts)


def build_recommendation(profile: dict[str, Any]) -> dict[str, Any]:
    """Full hybrid pipeline: rules decide, LLM explains, template guarantees."""
    plan = build_plan(profile)
    narrative_llm = explain_with_llm(plan["steps"], plan["stats_summary"])
    narrative = narrative_llm or explain_with_template(plan["steps"], profile)
    plan["narrative"] = narrative
    plan["generated_by"] = "rules+llm" if narrative_llm else "rules"
    plan["requires_approval"] = True
    return plan
