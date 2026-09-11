"""
AIDSE Platform — Project Report Builder (Phase 15)

One coherent JSON report per project, assembled from data that already
exists: dataset profiles, quality summaries, ML experiments/trials,
evaluation runs and baselines. No new computation beyond aggregation.

The report DATA MODEL is the deliverable; export formats arrive in V2.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.modules.automl.models import Experiment
from apps.api.modules.datasets.models import Dataset, GoldenDataset
from apps.api.modules.evaluation.models import EvaluationRun


async def build_project_report(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    # ── Datasets ─────────────────────────────────────────────────────────────
    ds_stmt = (
        select(Dataset)
        .options(selectinload(Dataset.versions))
        .where(Dataset.project_id == project_id)
    )
    datasets = (await db.execute(ds_stmt)).scalars().all()

    dataset_sections = []
    total_quality = {"critical": 0, "warning": 0, "info": 0}
    for d in datasets:
        latest = max(d.versions, key=lambda v: v.created_at, default=None)
        entry: dict[str, Any] = {
            "dataset_id": str(d.id),
            "name": d.name,
            "format": d.format,
            "versions": len(d.versions),
        }
        if latest and latest.profile_data and "error" not in latest.profile_data:
            p = latest.profile_data
            q = p.get("quality_issues_summary", {})
            entry.update({
                "latest_version": latest.version_tag,
                "profile_status": latest.profile_status or ("ready" if latest.profile_data else None),
                "num_rows": p.get("num_rows"),
                "num_columns": p.get("num_columns"),
                "duplicate_rows": p.get("duplicate_rows"),
                "quality": {
                    "critical": q.get("critical", 0),
                    "warning": q.get("warning", 0),
                    "info": q.get("info", 0),
                },
            })
            for k in total_quality:
                total_quality[k] += int(q.get(k) or 0)
        else:
            entry["profile_status"] = (latest.profile_status if latest else None) or "none"
        dataset_sections.append(entry)

    dataset_sections.sort(key=lambda x: x["name"].lower())

    # ── ML experiments ───────────────────────────────────────────────────────
    exp_stmt = (
        select(Experiment)
        .options(selectinload(Experiment.trials))
        .where(Experiment.project_id == project_id)
        .order_by(Experiment.created_at.desc())
    )
    experiments = (await db.execute(exp_stmt)).scalars().all()

    ml_sections = []
    for e in experiments:
        completed = [t for t in e.trials if t.status == "completed"]
        best = None
        if completed:
            lower_better = e.primary_metric in ("rmse", "mae", "mse")
            if lower_better:
                best = min(
                    completed,
                    key=lambda t: t.primary_metric_score if t.primary_metric_score is not None else float("inf"),
                )
            else:
                best = max(
                    completed,
                    key=lambda t: t.primary_metric_score if t.primary_metric_score is not None else float("-inf"),
                )

        ml_sections.append({
            "experiment_id": str(e.id),
            "target_column": e.target_column,
            "problem_type": e.problem_type,
            "primary_metric": e.primary_metric,
            "status": e.status,
            "trials_completed": len(completed),
            "best_model": {
                "algorithm": best.algorithm_name,
                "score": best.primary_metric_score,
            } if best else None,
        })

    # ── AI evaluations ───────────────────────────────────────────────────────
    gold_stmt = (
        select(GoldenDataset)
        .options(selectinload(GoldenDataset.cases))
        .where(GoldenDataset.project_id == project_id)
    )
    goldens = (await db.execute(gold_stmt)).scalars().all()

    run_stmt = (
        select(EvaluationRun)
        .join(GoldenDataset, EvaluationRun.golden_dataset_id == GoldenDataset.id)
        .where(GoldenDataset.project_id == project_id)
    )
    runs = (await db.execute(run_stmt)).scalars().all()
    runs_by_golden: dict[uuid.UUID, list[EvaluationRun]] = {}
    for r in runs:
        runs_by_golden.setdefault(r.golden_dataset_id, []).append(r)

    eval_sections = []
    for g in goldens:
        gruns = sorted(runs_by_golden.get(g.id, []), key=lambda r: r.started_at or r.completed_at or datetime.min.replace(tzinfo=timezone.utc))
        latest_run = gruns[-1] if gruns else None
        agg = (latest_run.aggregate_results or {}) if latest_run else {}
        baseline_set = bool(g.baseline_run_id)
        eval_sections.append({
            "golden_dataset_id": str(g.id),
            "name": g.name,
            "version": g.version,
            "case_count": len(g.cases),
            "baseline_designated": baseline_set,
            "total_runs": len(gruns),
            "latest_run": {
                "run_id": str(latest_run.id),
                "status": latest_run.status,
                "scoring_strategy": latest_run.scoring_strategy,
                "pass_rate": agg.get("pass_rate"),
                "critical_failures": (agg.get("per_tag", {}).get("critical", {}).get("total", 0)
                                      - agg.get("per_tag", {}).get("critical", {}).get("passed", 0))
                if agg.get("per_tag") else None,
            } if latest_run else None,
        })

    return {
        "project_id": str(project_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "datasets": len(datasets),
            "experiments": len(experiments),
            "golden_datasets": len(goldens),
            "evaluation_runs": len(runs),
            "data_quality_totals": total_quality,
        },
        "datasets": dataset_sections,
        "ml_results": ml_sections,
        "ai_evaluation": eval_sections,
    }
