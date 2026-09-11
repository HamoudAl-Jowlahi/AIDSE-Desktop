"""
AIDSE Platform — AI Evaluation Router (Phases 13-14)

Run lifecycle:
    POST /runs                      create + execute inline → completed/failed
    GET  /runs                      history (aggregates only)
    GET  /runs/{id}                 full run with per-case results
    POST /runs/{id}/regression-report   build/refresh diff vs baseline
    GET  /runs/{id}/regression-report   verdict + flaky detection
                                        (auto-builds the report if missing)
    GET  /runs/{id}/gate            CI gate — 406 when critical regressions

Golden-dataset CRUD lives in the datasets router.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.core.dependencies import get_db, require_project_role, ProjectRole, get_current_user
from apps.api.modules.auth.schemas import UserOut
from apps.api.modules.evaluation import models, schemas
from apps.api.modules.evaluation.runner import execute_run
from apps.api.modules.evaluation.scoring import STRATEGIES
from apps.api.modules.datasets.models import GoldenDataset
from apps.api.modules.projects.service import _write_audit_log

router = APIRouter(prefix="/projects/{project_id}/evaluations", tags=["Evaluations"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_run_or_404(db: AsyncSession, project_id: uuid.UUID, run_id: uuid.UUID,
                          with_results: bool = True) -> models.EvaluationRun:
    stmt = select(models.EvaluationRun).join(GoldenDataset).where(
        models.EvaluationRun.id == run_id,
        GoldenDataset.project_id == project_id,
    )
    if with_results:
        stmt = stmt.options(selectinload(models.EvaluationRun.results))
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


async def _build_regression_report(db: AsyncSession, project_id: uuid.UUID,
                                   run_id: uuid.UUID) -> models.RegressionReport:
    """
    Diff engine: compare the run to its golden dataset's baseline.
    Idempotent — recreates the report if one already exists.
    Returns the persisted ORM object.
    """
    stmt = (
        select(models.EvaluationRun)
        .options(selectinload(models.EvaluationRun.results))
        .join(GoldenDataset)
        .options(selectinload(models.EvaluationRun.golden_dataset).selectinload(GoldenDataset.cases))
        .where(models.EvaluationRun.id == run_id, GoldenDataset.project_id == project_id)
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    baseline_run_id = run.golden_dataset.baseline_run_id
    if not baseline_run_id:
        raise HTTPException(status_code=400, detail="No baseline designated for this golden dataset")
    if run.id == baseline_run_id:
        raise HTTPException(status_code=400, detail="Cannot compare a baseline to itself")

    baseline_stmt = (
        select(models.EvaluationRun)
        .options(selectinload(models.EvaluationRun.results))
        .where(models.EvaluationRun.id == baseline_run_id)
    )
    baseline_run = (await db.execute(baseline_stmt)).scalar_one_or_none()
    if not baseline_run:
        raise HTTPException(status_code=400, detail="Baseline run not found in database")

    # Replace any previous report for this run (idempotent refresh)
    existing = (
        await db.execute(
            select(models.RegressionReport).where(
                models.RegressionReport.evaluation_run_id == run.id
            )
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.flush()

    baseline_map = {res.golden_case_id: res for res in baseline_run.results}
    case_tags = {case.id: case.category_tag for case in run.golden_dataset.cases}

    report = models.RegressionReport(
        evaluation_run_id=run.id,
        baseline_run_id=baseline_run_id,
    )
    db.add(report)
    await db.flush()

    regressed = newly_passing = stable = critical_regressions = 0
    report_cases: list[models.RegressionReportCase] = []

    for res in run.results:
        base_res = baseline_map.get(res.golden_case_id)
        tag = case_tags.get(res.golden_case_id)

        transition = "Stable"
        baseline_score = None
        if base_res:
            baseline_score = base_res.score
            if base_res.status == "fail" and res.status == "pass":
                transition = "Newly Passing"
                newly_passing += 1
            elif base_res.status == "pass" and res.status == "fail":
                transition = "Regressed"
                regressed += 1
                if tag and tag.lower() == "critical":
                    critical_regressions += 1
            else:
                stable += 1
        else:
            stable += 1

        report_cases.append(models.RegressionReportCase(
            report_id=report.id,
            golden_case_id=res.golden_case_id,
            category_tag=tag,
            status_transition=transition,
            baseline_score=baseline_score,
            new_score=res.score,
        ))

    report.total_cases = len(run.results)
    report.regressed_cases = regressed
    report.newly_passing_cases = newly_passing
    report.stable_cases = stable
    report.critical_regressions = critical_regressions

    db.add_all(report_cases)
    await db.commit()

    final_stmt = (
        select(models.RegressionReport)
        .options(selectinload(models.RegressionReport.cases))
        .where(models.RegressionReport.id == report.id)
    )
    return (await db.execute(final_stmt)).scalar_one()


async def _golden_dataset_of(db: AsyncSession, project_id: uuid.UUID,
                             run_id: uuid.UUID) -> uuid.UUID:
    stmt = (
        select(models.EvaluationRun.golden_dataset_id)
        .join(GoldenDataset, models.EvaluationRun.golden_dataset_id == GoldenDataset.id)
        .where(models.EvaluationRun.id == run_id, GoldenDataset.project_id == project_id)
    )
    return (await db.execute(stmt)).scalar_one()


def _run_to_response(r: models.EvaluationRun, include_results: bool = True) -> schemas.EvaluationRunResponse:
    return schemas.EvaluationRunResponse(
        id=r.id,
        golden_dataset_id=r.golden_dataset_id,
        provider=r.provider,
        prompt_config_hash=r.prompt_config_hash,
        scoring_strategy=r.scoring_strategy,
        scoring_params=r.scoring_params,
        status=r.status,
        aggregate_results=r.aggregate_results,
        started_at=r.started_at,
        completed_at=r.completed_at,
        results=[
            schemas.EvaluationResultResponse(
                id=res.id,
                evaluation_run_id=res.evaluation_run_id,
                golden_case_id=res.golden_case_id,
                actual_output=res.actual_output,
                score=res.score,
                status=res.status,
                scoring_detail=res.scoring_detail,
            )
            for res in (r.results or [])
        ] if include_results else [],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Runs
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/runs", response_model=schemas.EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
async def create_evaluation_run(
    project_id: uuid.UUID,
    run_in: schemas.EvaluationRunCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
    current_user: UserOut = Depends(get_current_user),
):
    """Phase 17: state-changing action — audited."""
    """
    Create AND execute an evaluation run against a golden dataset (Phase 13).

    Outputs come from actual_outputs; when absent, a configured evaluation
    provider would generate them. The chosen strategy grades every case and
    aggregates are stored before the response returns.
    """
    if run_in.scoring_strategy not in STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown strategy '{run_in.scoring_strategy}'. Supported: {', '.join(STRATEGIES)}.",
        )

    stmt = (
        select(GoldenDataset)
        .options(selectinload(GoldenDataset.cases))
        .where(GoldenDataset.id == run_in.golden_dataset_id,
               GoldenDataset.project_id == project_id)
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Golden dataset not found in this project")
    if not dataset.cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Golden dataset has no cases to evaluate.")

    run = models.EvaluationRun(
        golden_dataset_id=run_in.golden_dataset_id,
        provider=run_in.provider,
        prompt_config_hash=run_in.prompt_config_hash,
        scoring_strategy=run_in.scoring_strategy,
        scoring_params=run_in.scoring_params or {},
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    try:
        await execute_run(db, run.id, run_in.scoring_strategy,
                          run_in.scoring_params or {}, run_in.actual_outputs, None)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        run.status = "failed"
        run.aggregate_results = {"error": str(exc)[:500]}
        db.add(run)
        await db.commit()

    # The session's cached instance predates the new results (identity map +
    # expire_on_commit=False); expire so the eager re-select sees fresh rows.
    final_run_id = run.id  # capture BEFORE expiring — access would lazy-load
    db.expire(run)

    await _write_audit_log(
        db,
        project_id=project_id,
        actor_id=current_user.id,
        action="evaluation.run.executed",
        target_type="evaluation_run",
        target_id=final_run_id,
        metadata={"strategy": run_in.scoring_strategy, "golden_dataset_id": str(run_in.golden_dataset_id)},
    )
    await db.commit()

    return await _get_run_or_404(db, project_id, final_run_id)


@router.get("/runs", response_model=List[schemas.EvaluationRunResponse])
async def list_evaluation_runs(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """Run history (aggregates included, nested results omitted for size)."""
    stmt = (
        select(models.EvaluationRun)
        .join(GoldenDataset)
        .where(GoldenDataset.project_id == project_id)
        .order_by(models.EvaluationRun.id.desc())
        .limit(min(limit, 200))
    )
    if golden_dataset_id:
        stmt = stmt.where(models.EvaluationRun.golden_dataset_id == golden_dataset_id)

    runs = (await db.execute(stmt)).scalars().all()
    return [_run_to_response(r, include_results=False) for r in runs]


@router.get("/runs/{run_id}", response_model=schemas.EvaluationRunResponse)
async def get_evaluation_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """Full run including per-case results."""
    run = await _get_run_or_404(db, project_id, run_id)
    return _run_to_response(run)


# ──────────────────────────────────────────────────────────────────────────────
# Regression reporting (Phase 14)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/runs/{run_id}/regression-report",
             response_model=schemas.RegressionReportResponse,
             status_code=status.HTTP_201_CREATED)
async def generate_regression_report(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """Generate (or refresh) the regression report versus baseline."""
    report = await _build_regression_report(db, project_id, run_id)
    stmt = (
        select(models.RegressionReport)
        .options(selectinload(models.RegressionReport.cases))
        .where(models.RegressionReport.id == report.id)
    )
    return (await db.execute(stmt)).scalar_one()


@router.get("/runs/{run_id}/regression-report", response_model=schemas.RegressionVerdictOut)
async def get_regression_report(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Regression report PLUS computed verdict (PASS/WARN/FAIL) and
    flaky-case detection across this dataset's run history.
    Auto-builds the report on first view.
    """
    try:
        report = await _build_regression_report(db, project_id, run_id)
    except HTTPException as exc:
        if exc.status_code == 400 and "No baseline" in str(exc.detail):
            raise HTTPException(status_code=400, detail=str(exc.detail))
        raise

    base = schemas.RegressionReportResponse(
        evaluation_run_id=report.evaluation_run_id,
        baseline_run_id=report.baseline_run_id,
        total_cases=report.total_cases,
        regressed_cases=report.regressed_cases,
        newly_passing_cases=report.newly_passing_cases,
        stable_cases=report.stable_cases,
        critical_regressions=report.critical_regressions,
        cases=[
            schemas.RegressionReportCaseResponse(
                golden_case_id=c.golden_case_id,
                category_tag=c.category_tag,
                status_transition=c.status_transition,
                baseline_score=c.baseline_score,
                new_score=c.new_score,
            )
            for c in report.cases
        ],
    )

    if report.critical_regressions > 0:
        verdict = "FAIL"
        reason = (f"{report.critical_regressions} case(s) tagged 'critical' regressed. "
                  "Do not ship this change.")
    elif report.regressed_cases > 0:
        verdict = "WARN"
        reason = f"{report.regressed_cases} case(s) regressed (none tagged critical). Review before shipping."
    elif report.newly_passing_cases > 0:
        verdict = "PASS"
        reason = f"No regressions; {report.newly_passing_cases} case(s) newly pass."
    else:
        verdict = "PASS"
        reason = "No status changes versus baseline."

    # Flaky detection: statuses across ALL runs of this golden dataset,
    # ordered by execution time (UUIDs are NOT chronological).
    flaky: list[schemas.FlakyCaseOut] = []
    golden_id = await _golden_dataset_of(db, project_id, run_id)
    sibling_ids = [
        r[0] for r in (
            await db.execute(
                select(models.EvaluationRun.id).where(
                    models.EvaluationRun.golden_dataset_id == golden_id
                )
            )
        ).all()
    ]

    if len(sibling_ids) >= 3:
        res_stmt = (
            select(
                models.EvaluationResult.golden_case_id,
                models.EvaluationResult.status,
            )
            .join(models.EvaluationRun,
                  models.EvaluationResult.evaluation_run_id == models.EvaluationRun.id)
            .where(models.EvaluationResult.evaluation_run_id.in_(sibling_ids))
            .order_by(models.EvaluationRun.started_at.asc().nullslast())
        )
        history: dict[uuid.UUID, list[str]] = {}
        for cid, st in (await db.execute(res_stmt)).all():
            history.setdefault(cid, []).append(st)

        for c in report.cases:
            statuses = history.get(c.golden_case_id, [])
            flips = sum(1 for a, b in zip(statuses, statuses[1:]) if a != b)
            if flips >= 2:
                flaky.append(schemas.FlakyCaseOut(
                    golden_case_id=c.golden_case_id,
                    category_tag=c.category_tag,
                    observed_statuses=statuses[-5:],
                    note=f"Result flipped {flips} times across {len(statuses)} runs.",
                ))

    score_changed = sum(
        1 for c in report.cases
        if c.status_transition == "Stable" and c.baseline_score is not None
        and abs((c.new_score or 0) - c.baseline_score) > 1e-9
    )

    return schemas.RegressionVerdictOut(
        **base.model_dump(),
        verdict=verdict,
        verdict_reason=reason,
        score_changed_cases=score_changed,
        flaky_cases=flaky,
    )


@router.get("/runs/{run_id}/gate")
async def get_regression_gate_status(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    CI-callable gate: 200 {pass:true} when clean, 406 when critical regressions.
    """
    stmt = (
        select(models.RegressionReport)
        .join(models.EvaluationRun,
              models.RegressionReport.evaluation_run_id == models.EvaluationRun.id)
        .join(GoldenDataset, models.EvaluationRun.golden_dataset_id == GoldenDataset.id)
        .where(models.RegressionReport.evaluation_run_id == run_id,
               GoldenDataset.project_id == project_id)
    )
    report = (await db.execute(stmt)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Regression report not found for this run")

    if report.critical_regressions > 0:
        return JSONResponse(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            content={"pass": False, "critical_regressions": report.critical_regressions},
        )
    return {"pass": True, "critical_regressions": 0}


# ──────────────────────────────────────────────────────────────────────────────
# Schedules (V3 scope — stored config only)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/schedules", response_model=schemas.ScheduledEvaluationResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_evaluation(
    project_id: uuid.UUID,
    schedule_in: schemas.ScheduledEvaluationCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    stmt = select(GoldenDataset).where(
        GoldenDataset.id == schedule_in.golden_dataset_id,
        GoldenDataset.project_id == project_id,
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Golden dataset not found in this project")

    schedule = models.ScheduledEvaluation(
        golden_dataset_id=schedule_in.golden_dataset_id,
        provider=schedule_in.provider,
        cron_expression=schedule_in.cron_expression,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/schedules", response_model=List[schemas.ScheduledEvaluationResponse])
async def list_scheduled_evaluations(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    stmt = (
        select(models.ScheduledEvaluation)
        .join(GoldenDataset)
        .where(GoldenDataset.project_id == project_id)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
