import asyncio
import logging
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

logger = logging.getLogger("aidse.automl")

# asyncio holds only a weak reference to a running task, so a bare
# create_task() can be garbage-collected mid-training and vanish silently.
# Keeping a strong reference until the task completes is the documented fix.
_background_training: set[asyncio.Task] = set()


def _spawn_local_training(experiment_id: str) -> None:
    """Run an experiment in-process and keep the task alive until it finishes."""
    from apps.api.core.config import get_settings
    from apps.api.modules.automl.service import _run_automl_async

    if not get_settings().LOCAL_TRAINING_FALLBACK:
        logger.info(
            "No broker reachable and the local training fallback is disabled; "
            "experiment %s stays pending.", experiment_id,
        )
        return

    task = asyncio.create_task(_run_automl_async(experiment_id))
    _background_training.add(task)

    def _done(finished: asyncio.Task) -> None:
        _background_training.discard(finished)
        if finished.cancelled():
            logger.warning("Training task for experiment %s was cancelled.", experiment_id)
            return
        exc = finished.exception()
        if exc is not None:
            logger.error(
                "Training task for experiment %s failed: %s", experiment_id, exc,
                exc_info=exc,
            )

    task.add_done_callback(_done)

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

    # Train in-process. This used to try a Celery broker first, which is what
    # made the endpoint hang: connect_timeout bounded the broker dial, but the
    # redis result backend retried separately — twenty attempts a second apart —
    # so creating an experiment blocked the request, and the UI with it, for
    # over twenty seconds on any machine without Redis. That is every desktop
    # install, so the worker and its broker are gone.
    _spawn_local_training(str(experiment.id))

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
