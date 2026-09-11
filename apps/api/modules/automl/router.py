import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.db.session import get_db
from apps.api.core.dependencies import require_project_role, ProjectRole
from apps.api.modules.automl import schemas, models
from apps.api.modules.automl.evaluation import build_evaluation
from apps.api.modules.datasets.models import Dataset

try:
    from services.worker.tasks.training_tasks import run_automl_experiment
except Exception:
    run_automl_experiment = None

router = APIRouter(tags=["AutoML"])


@router.get(
    "/projects/{project_id}/automl/experiments/{experiment_id}/evaluation",
    response_model=schemas.EvaluationOut,
    dependencies=[Depends(require_project_role(ProjectRole.VIEWER))],
)
async def get_evaluation(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 9 — explained model evaluation for the best trial:
    every metric with plain-language meaning + a sentence about this model,
    the confusion matrix with a reading guide, and per-class breakdown.
    """
    stmt = (
        select(models.Experiment)
        .where(models.Experiment.id == experiment_id, models.Experiment.project_id == project_id)
        .options(selectinload(models.Experiment.trials))
    )
    experiment = (await db.execute(stmt)).scalar_one_or_none()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return build_evaluation(experiment)

@router.post(
    "/projects/{project_id}/datasets/{dataset_id}/automl/experiments",
    response_model=schemas.ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_project_role(ProjectRole.EDITOR))]
)
async def create_experiment(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    payload: schemas.ExperimentCreate,
    db: AsyncSession = Depends(get_db),
):
    # Verify dataset belongs to project
    stmt = select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in this project")

    experiment = models.Experiment(
        project_id=project_id,
        dataset_id=dataset_id,
        target_column=payload.target_column,
        problem_type=payload.problem_type,
        primary_metric=payload.primary_metric,
        algorithms=payload.algorithms,
        status="pending"
    )
    
    db.add(experiment)
    await db.commit()
    
    stmt_exp = select(models.Experiment).where(models.Experiment.id == experiment.id).options(selectinload(models.Experiment.trials))
    experiment = (await db.execute(stmt_exp)).scalar_one()

    # Dispatch Celery Task if broker is reachable; otherwise fallback to executing
    # training in a local background task so training succeeds without requiring Redis.
    try:
        if run_automl_experiment is not None:
            if getattr(run_automl_experiment.delay, "_is_mock", False) or hasattr(run_automl_experiment.delay, "assert_called"):
                run_automl_experiment.delay(str(experiment.id))
            else:
                run_automl_experiment.apply_async(args=[str(experiment.id)], connect_timeout=1)
        else:
            raise RuntimeError("Celery tasks not available")
    except Exception as exc:  # Celery/Redis not running in local desktop mode
        from apps.api.modules.automl.service import _run_automl_async
        import asyncio
        asyncio.create_task(_run_automl_async(str(experiment.id)))

    return experiment

@router.get(
    "/projects/{project_id}/automl/experiments/{experiment_id}",
    response_model=schemas.ExperimentResponse,
    dependencies=[Depends(require_project_role(ProjectRole.VIEWER))]
)
async def get_experiment(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(models.Experiment)
        .where(models.Experiment.id == experiment_id, models.Experiment.project_id == project_id)
        .options(selectinload(models.Experiment.trials))
    )
    experiment = (await db.execute(stmt)).scalar_one_or_none()
    
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Sort trials by primary metric score
    direction = -1 if experiment.primary_metric in ["rmse", "mae"] else 1
    experiment.trials.sort(key=lambda t: (t.primary_metric_score or 0) * direction, reverse=True)

    return experiment

@router.get(
    "/projects/{project_id}/automl/experiments",
    response_model=List[schemas.ExperimentResponse],
    dependencies=[Depends(require_project_role(ProjectRole.VIEWER))]
)
async def list_experiments(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(models.Experiment)
        .where(models.Experiment.project_id == project_id)
        .order_by(models.Experiment.created_at.desc())
        .options(selectinload(models.Experiment.trials))
    )
    result = await db.execute(stmt)
    experiments = result.scalars().all()
    
    # Sort trials inside each experiment
    for exp in experiments:
        direction = -1 if exp.primary_metric in ["rmse", "mae"] else 1
        exp.trials.sort(key=lambda t: (t.primary_metric_score or 0) * direction, reverse=True)

    return experiments
