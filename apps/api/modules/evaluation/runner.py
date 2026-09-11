"""
AIDSE Platform — Evaluation Run Executor (Phase 13)

Turns a "pending" EvaluationRun row into a completed one:

    for each golden case:
        actual = provided output OR provider-generated (if configured)
        {score, passed, detail} = score_case(strategy, expected, actual)
        write EvaluationResult
    aggregate → pass rate, mean score, per-tag breakdown
    run.status → completed | failed (never left pending)

Runs inline: golden datasets are small (tens of cases) and every strategy
is fast; a broker round-trip adds fragility without V1 benefit.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.modules.datasets.models import GoldenCase
from apps.api.modules.evaluation import models
from apps.api.modules.evaluation.scoring import score_case

logger = logging.getLogger(__name__)


async def execute_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    strategy: str,
    scoring_params: dict[str, Any] | None,
    actual_outputs: dict[str, str] | None,
    case_inputs: dict[str, str] | None,
) -> models.EvaluationRun:
    """Execute and finalize the run. Caller owns the session/commit."""
    stmt = (
        select(models.EvaluationRun)
        .where(models.EvaluationRun.id == run_id)
        .options(selectinload(models.EvaluationRun.results))
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise ValueError("Run not found during execution.")

    cases_stmt = (
        select(GoldenCase)
        .where(GoldenCase.golden_dataset_id == run.golden_dataset_id)
    )
    cases = list((await db.execute(cases_stmt)).scalars().all())
    if not cases:
        run.status = "failed"
        run.aggregate_results = {"error": "Golden dataset has no cases to evaluate."}
        return run

    outputs = dict(actual_outputs or {})
    inputs = dict(case_inputs or {})

    # Clear any stale results from a previous attempt
    for old in run.results:
        await db.delete(old)
    await db.flush()

    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    await db.flush()

    scores: list[float] = []
    passed_count = 0
    per_tag: dict[str, dict[str, int]] = {}
    failures: list[str] = []

    try:
        for case in cases:
            case_id_str = str(case.id)
            if case_id_str in outputs:
                actual = outputs[case_id_str]
            else:
                raise ValueError(
                    f"No actual output supplied for case {case_id_str}. "
                    "Provide actual_outputs or configure an evaluation provider."
                )
            # score_case can block for a long time: `regex` runs a user-authored
            # pattern with no engine timeout (a catastrophic one backtracks
            # indefinitely), and `llm_judge` makes a synchronous HTTP call.
            # Keep both off the event loop so the UI stays responsive.
            scored = await asyncio.to_thread(
                score_case, strategy, case.expected_output, actual, scoring_params
            )

            status_word = "pass" if scored["passed"] else "fail"
            db.add(models.EvaluationResult(
                evaluation_run_id=run.id,
                golden_case_id=case.id,
                actual_output=actual,
                score=scored["score"],
                status=status_word,
                scoring_detail=scored["detail"] | {
                    "expected_output": case.expected_output,
                    "strategy": strategy,
                },
            ))
            scores.append(scored["score"])
            passed_count += 1 if scored["passed"] else 0

            tag = case.category_tag or "untagged"
            bucket = per_tag.setdefault(tag, {"total": 0, "passed": 0})
            bucket["total"] += 1
            bucket["passed"] += 1 if scored["passed"] else 0

            if not scored["passed"]:
                failures.append({
                    "golden_case_id": case_id_str,
                    "input": case.input_data[:200],
                    "expected": case.expected_output[:200],
                    "actual": actual[:200],
                    "score": scored["score"],
                    "tag": case.category_tag,
                })

        run.aggregate_results = {
            "scoring_strategy": strategy,
            "total_cases": len(cases),
            "passed_cases": passed_count,
            "failed_cases": len(cases) - passed_count,
            "pass_rate": round(passed_count / len(cases), 4) if cases else 0.0,
            "mean_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "per_tag": per_tag,
            "failure_details": failures[:25],
        }
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)

    except Exception as exc:
        logger.exception("Evaluation run %s failed", run_id)
        run.status = "failed"
        run.aggregate_results = {"error": str(exc)[:500]}
        run.completed_at = datetime.now(timezone.utc)

    return run


# Provider-side generation hook (used when no outputs are supplied).
def generate_output_via_provider(prompt: str) -> str:
    """
    Optional helper: generate an actual output with the configured provider.
    Raises when unconfigured so callers can ask the user instead.
    """
    from apps.api.core.config import get_settings

    settings = get_settings()
    if not (settings.LLM_PROVIDER in ("openai", "anthropic") and settings.LLM_API_KEY):
        raise RuntimeError("No evaluation provider configured.")

    import httpx

    if settings.LLM_PROVIDER == "openai":
        url = (settings.LLM_BASE_URL or "https://api.openai.com/v1") + "/chat/completions"
        headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
        payload = {
            "model": settings.LLM_MODEL or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
    else:
        url = settings.LLM_BASE_URL or "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": settings.LLM_API_KEY, "anthropic-version": "2023-06-01"}
        payload = {
            "model": settings.LLM_MODEL or "claude-3-5-haiku-latest",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }

    resp = httpx.post(url, headers=headers, json=payload, timeout=settings.LLM_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    if settings.LLM_PROVIDER == "openai":
        return data["choices"][0]["message"]["content"]
    return data["content"][0]["text"]
