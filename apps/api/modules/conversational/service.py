"""
AIDSE Platform — Analyst Orchestration (Phase 11)

Anti-fabrication architecture:

    user question
        │
        ▼
   ┌─────────────┐   picks tools    ┌──────────────────┐
   │  Router      │ ───────────────▶│ SAFE TOOLS execute │──▶ REAL numbers
   │ (LLM or rules)│                └──────────────────┘
   └─────────────┘                        │
        ▲                                 ▼
        └──────── answer is composed FROM tool results ONLY

Two router modes, both honest:
- "llm"      : the provider receives tool SCHEMAS and returns tool CALLS;
               numbers flow exclusively from executed tools.
- "fallback" : keyword routing runs the same tools deterministically.
               Active whenever no provider is configured — the product
               never degrades to invented statistics.

If a question matches no tool, the assistant says so and offers the list
of what it CAN answer. It never guesses.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from apps.api.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_LLM_ITERATIONS = 3

SYSTEM_PROMPT = (
    "You are AIDSE's AI Data Analyst. You answer questions about ONE dataset.\n"
    "STRICT RULES:\n"
    "1. Any number in your answer MUST come from a tool result provided to you.\n"
    "2. Never estimate, extrapolate or invent statistics.\n"
    "3. If no tool can answer the question, say so plainly and list what you can answer.\n"
    "4. Prefer short answers: the key number(s), then one sentence of interpretation.\n"
    "You call at most a few tools per question; results arrive as JSON."
)

# Keyword routes for the deterministic fallback mode.
_FALLBACK_ROUTES: list[tuple[tuple[str, ...], str]] = [
    (("missing", "null", "nan", "empty"), "missing_value_analysis"),
    (("correlat", "related", "relationship", "associated"), "correlation_analysis"),
    (("distribution", "histogram", "spread", "skew"), "distribution_analysis"),
    (("summar", "overview", "describe", "shape", "rows", "columns", "how big"), "dataset_summary"),
    (("quality", "problem", "issue", "clean"), "data_quality_overview"),
    (("preprocess", "impute", "encoding", "scale", "recommend"), "preprocessing_recommendation"),
    (("feature importance", "important feature", "influence", "driving"), "feature_importance"),
    (("confusion", "evaluation result"), "evaluation_results"),
    (("metric", "accuracy", "f1", "recall", "precision", "r2", "rmse", "auc", "model performance"), "model_metrics"),
]


def route_without_llm(question: str) -> tuple[str | None, dict[str, Any]]:
    """Pick (tool_name, args) from keywords. Returns (None, {}) when unsure."""
    q = question.lower()

    # Column-specific intents first
    for marker in ("distribution", "skew"):
        if marker in q:
            column = _extract_column_hint(question)
            if column:
                return "distribution_analysis", {"column": column}
    if ("missing" in q or "null" in q or "nan" in q) :
        column = _extract_column_hint(question)
        if column and ("in " in q or "of " in q):
            # "how many missing values are in age?" → column stats covers it precisely
            return "column_statistics", {"column": column}
    if ("correlat" in q or "related" in q) and ("target" in q or "label" in q):
        return "correlation_analysis", {}

    for keywords, tool in _FALLBACK_ROUTES:
        if any(k in q for k in keywords):
            args: dict[str, Any] = {}
            column = _extract_column_hint(question)
            if tool in ("column_statistics", "distribution_analysis") and column:
                args["column"] = column
            return tool, args
    return None, {}


def _extract_column_hint(question: str) -> str | None:
    """
    Best-effort extraction of a quoted word / known column name from the
    question. The caller validates against real columns anyway, so this only
    needs to find a candidate token after 'of', 'in', 'for' or inside quotes.
    """
    import re

    quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"|`([^`]+)`", question)
    for groups in quoted:
        for g in groups:
            if g:
                return g.strip()
    m = re.search(r"\b(?:of|in|for)\s+([A-Za-z_][A-Za-z0-9_]*)\b\??", question)
    if m:
        token = m.group(1)
        stopwords = {"the", "this", "dataset", "each", "all", "column", "model", "target"}
        if token.lower() not in stopwords:
            return token
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Answer composition (deterministic mode)
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_pct(value) -> str:
    """Human-friendly percentage: 15.0 → '15%', 15.55 → '15.55%'."""
    try:
        num = round(float(value), 2)
        if num == int(num):
            return f"{int(num)}%"
        return f"{num}%"
    except (TypeError, ValueError):
        return f"{value}%"


def compose_answer(tool_name: str, result: dict[str, Any]) -> str:
    """Turn a tool payload into a compact human answer WITHOUT adding numbers."""
    if not isinstance(result, dict):
        return "No information could be extracted for this query."

    if tool_name == "dataset_summary":
        num_rows = result.get("num_rows")
        num_columns = result.get("num_columns")
        if num_rows is None and num_columns is None:
            return "No dataset is currently selected. Please select a dataset from the dropdown above to view its summary."
        rows_str = f"{num_rows:,}" if isinstance(num_rows, (int, float)) else "Unknown"
        cols_str = str(num_columns) if num_columns is not None else "Unknown"
        missing_cells = result.get("missing_cells")
        missing_str = f"{missing_cells:,}" if isinstance(missing_cells, (int, float)) else "0"
        return (
            f"The dataset has {rows_str} rows and {cols_str} columns. "
            f"{result.get('duplicate_rows') or 0} duplicate rows and {missing_str} missing cells were found. "
            + (f"Suggested target column: '{result.get('target_candidate')}'." if result.get("target_candidate") else "")
        ).strip()
    if tool_name == "column_statistics":
        col = result.get("column")
        if not col:
            return "Please select a dataset and specify a column name to view statistics."
        bits = [f"'{col}' is {result.get('semantic_type', 'unknown')}"]
        if result.get("missing_pct") is not None:
            bits.append(f"{_fmt_pct(result['missing_pct'])} of values are missing")
        if result.get("mean") is not None:
            bits.append(f"mean {round(result['mean'], 3)}, median {round(result.get('median', 0), 3)}")
        elif result.get("most_frequent"):
            top = next(iter(result["most_frequent"].items()))
            bits.append(f"most frequent value: {top[0]} ({top[1]} rows)")
        if result.get("unique_values") is not None:
            bits.append(f"{result['unique_values']} distinct values")
        return ". ".join(bits) + "."
    if tool_name == "missing_value_analysis":
        if not result or "total_missing_cells" not in result:
            return "No dataset selected. Please select a dataset to inspect missing values."
        tot = result.get("total_missing_cells") or 0
        if tot == 0:
            return "No missing values anywhere in this dataset — every column is complete."
        worst = list((result.get("per_column") or {}).items())[:5]
        listing = ", ".join(
            f"'{c}' {_fmt_pct(v.get('null_pct', 0))}" for c, v in worst
        )
        share = _fmt_pct(result.get("missing_share_of_all_cells_pct", 0))
        return (
            f"{tot:,} cells are missing ({share} of all cells). Worst columns: {listing}."
        )
    if tool_name == "correlation_analysis":
        pairs = result.get("pairs_involving_target") or result.get("strong_pairs") or []
        if not pairs:
            return "No correlation pairs above |0.6| were found or stored for this dataset."
        listing = ", ".join(f"'{p.get('a', '')}' × '{p.get('b', '')}' r={p.get('r', '')}" for p in pairs[:5])
        return f"Strongest correlations: {listing}."
    if tool_name == "distribution_analysis":
        col = result.get("column")
        if not col:
            return "Please select a dataset and column to view distribution."
        line = f"'{col}' is {result.get('shape_note', 'analyzed')}."
        if result.get("histogram") and result["histogram"].get("counts") and result["histogram"].get("bin_edges"):
            counts = result["histogram"]["counts"]
            edges = result["histogram"]["bin_edges"]
            if counts and len(edges) > 1:
                peak = counts.index(max(counts))
                peak_next = min(peak + 1, len(edges) - 1)
                line += f" Most values fall between {edges[peak]:.3g} and {edges[peak_next]:.3g} ({max(counts):,} rows)."
        elif result.get("category_counts"):
            cc = result["category_counts"]
            line += " Categories: " + ", ".join(f"{k} ({v})" for k, v in list(cc.items())[:6]) + "."
        return line
    if tool_name == "data_quality_overview":
        s = result.get("summary", {})
        if not s and not result.get("issues"):
            return "No data quality issues found or no dataset is currently selected."
        lines = [f"Quality scan: {s.get('critical', 0)} critical, {s.get('warning', 0)} warning, {s.get('info', 0)} info issues."]
        lines += [f"[{i.get('severity', 'info').upper()}] {i.get('title', '')} → suggested fix: {i.get('recommendation', '')}" for i in result.get("issues", [])[:8]]
        return "\n".join(lines)
    if tool_name == "preprocessing_recommendation":
        steps = result.get("steps", [])
        if not steps:
            return result.get("narrative") or "No preprocessing appears necessary right now."
        listing = "\n".join(f"{s['order']}. {s['action']} on {s['column']} — {s['why']}" for s in steps[:10])
        return f"Recommended plan ({len(steps)} steps, approval required):\n{listing}"
    if tool_name == "model_metrics":
        if not result.get("metrics"):
            return "No trained model found yet — train one in the ML Lab and ask again."
        best = result.get("best_algorithm") or "the best model"
        lines = [f"Best model: {best.replace('_', ' ')}."]
        lines += [f"- {m['metric']}: {m['value']} — {m['interpretation']}" for m in result["metrics"][:6]]
        return "\n".join(lines)
    if tool_name == "feature_importance":
        tops = list(result.get("top_features", {}).items())
        if not tops:
            return result.get("insight") or "No importance data available yet."
        listing = ", ".join(f"'{k}' ({round(v, 4)})" for k, v in tops[:5])
        return f"Most influential features: {listing}."
    if tool_name == "evaluation_results":
        cm = result.get("confusion_matrix")
        base = "\n".join(f"- {m['metric']}: {m['value']} — {m['interpretation']}" for m in result.get("metrics", [])[:6])
        if cm:
            base += f"\nConfusion matrix labels: {cm['labels']}; matrix: {cm['matrix']}."
        return base or "No evaluation available yet."
    return json.dumps(result)[:800]


# ──────────────────────────────────────────────────────────────────────────────
# Main entrypoint
# ──────────────────────────────────────────────────────────────────────────────

def analyze_question(
    question: str,
    profile: dict[str, Any] | None,
    context_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Full pipeline for one question.

    context_payload carries pre-loaded artifacts keyed for tools:
      _quality_report, _recommendation_plan, _evaluation, _global_explanation
    (any may be absent → dependent tools raise clean ValueErrors).

    Returns {answer, tools_used, generated_by}.
    """
    settings = get_settings()
    llm_on = settings.LLM_PROVIDER in ("openai", "anthropic") and bool(settings.LLM_API_KEY)

    if not llm_on:
        return _run_fallback(question, profile, context_payload)
    try:
        return _run_llm(question, profile, context_payload, settings)
    except Exception as exc:
        logger.warning("LLM chat failed (%s); using deterministic fallback.", exc)
        return _run_fallback(question, profile, context_payload)


def _run_fallback(question: str, profile, context_payload) -> dict[str, Any]:
    from apps.api.modules.conversational.tools import execute_tool, TOOLS

    tool_name, args = route_without_llm(question)
    if tool_name is None:
        return {
            "answer": (
                "I can't determine that from the dataset without guessing, and I don't guess. "
                "Ask me about: dataset summary, missing values, one column's statistics, "
                "correlations, a column's distribution, data-quality issues, preprocessing "
                "recommendations, or the trained model's metrics and evaluation."
            ),
            "tools_used": [],
            "generated_by": "rules",
        }

    dataset_scoped_tools = {
        "dataset_summary", "column_statistics", "missing_value_analysis",
        "correlation_analysis", "distribution_analysis", "data_quality_overview",
        "preprocessing_recommendations",
    }
    if not profile and tool_name in dataset_scoped_tools:
        return {
            "answer": (
                "No dataset is currently selected. Please select or upload a dataset in this project "
                "from the dropdown above to analyze its summary, columns, missing values, or correlations."
            ),
            "tools_used": [],
            "generated_by": "rules",
        }

    # Validate column args against the real profile before executing
    if profile and args.get("column") and args["column"] not in profile.get("columns", {}):
        match = _fuzzy_column(args["column"], list(profile["columns"]))
        if match:
            args["column"] = match
        else:
            return {
                "answer": (
                    f"I couldn't find a column called '{args['column']}' in this dataset. "
                    f"Available columns include: {', '.join(list(profile.get('columns', {}))[:15])}."
                ),
                "tools_used": [{"tool": tool_name, "args": args}],
                "generated_by": "rules",
            }

    merged_args = {**(context_payload.get("_tool_args_extra", {})), **args}
    try:
        result = execute_tool(tool_name, profile or {}, merged_args)
    except ValueError as exc:
        return {
            "answer": f"I couldn't complete that analysis: {exc}",
            "tools_used": [{"tool": tool_name, "args": args}],
            "generated_by": "rules",
        }
    return {
        "answer": compose_answer(tool_name, result),
        "tools_used": [{"tool": tool_name, "args": args, "key_numbers": _extract_key_numbers(result)}],
        "generated_by": "rules",
    }


def _fuzzy_column(hint: str, columns: list[str]) -> str | None:
    hint_lower = hint.lower()
    exact = next((c for c in columns if c.lower() == hint_lower), None)
    if exact:
        return exact
    partial = [c for c in columns if hint_lower in c.lower()]
    return partial[0] if len(partial) == 1 else None


def _extract_key_numbers(result: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    """Small audit snapshot of the numbers that fed the answer."""
    flat: dict[str, Any] = {}
    def walk(prefix: str, node: Any) -> None:
        if len(flat) >= limit:
            return
        if isinstance(node, dict):
            for k, v in list(node.items())[:limit]:
                walk(f"{prefix}{k}.", v)
        elif isinstance(node, (int, float, str)) and not isinstance(node, bool):
            flat[prefix.rstrip(".")] = node
    walk("", result)
    return flat


# ──────────────────────────────────────────────────────────────────────────────
# LLM mode — provider chooses tools; results come back as JSON
# ──────────────────────────────────────────────────────────────────────────────

def _openai_tools_spec() -> list[dict[str, Any]]:
    from apps.api.modules.conversational.tools import TOOLS
    return [
        {"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.parameters,
        }}
        for t in TOOLS.values()
    ]


def _run_llm(question: str, profile, context_payload, settings) -> dict[str, Any]:
    import httpx
    from apps.api.modules.conversational.tools import execute_tool, TOOLS

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools_used: list[dict[str, Any]] = []

    url = (settings.LLM_BASE_URL or "https://api.openai.com/v1") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}

    final_text = None
    for _ in range(MAX_LLM_ITERATIONS):
        resp = httpx.post(url, headers=headers, timeout=settings.LLM_TIMEOUT_SECONDS, json={
            "model": settings.LLM_MODEL or "gpt-4o-mini",
            "messages": messages,
            "tools": _openai_tools_spec(),
            "temperature": 0.2,
        })
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]

        calls = choice.get("tool_calls") or []
        if not calls:
            final_text = choice.get("content") or ""
            break

        messages.append(choice)
        for call in calls[:3]:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = execute_tool(name, profile or {}, {**context_payload, **args})
                content = json.dumps(result)[:4000]
            except ValueError as exc:
                content = json.dumps({"error": str(exc)})
            tools_used.append({"tool": name, "args": args})
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": content,
            })

    if final_text is None:
        final_text = "(The analyst stopped early — please rephrase.)"

    return {
        "answer": final_text,
        "tools_used": tools_used,
        "generated_by": "rules+llm",
    }
