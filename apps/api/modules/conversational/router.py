"""
AIDSE Platform — AI Data Analyst Router (Phase 11)

POST /projects/{pid}/chat          — ask a question (optionally dataset-scoped)
GET  /projects/{pid}/chat/history  — latest conversation messages
                                     (optionally filtered by dataset)
DELETE /projects/{pid}/chat        — clear the conversation for a scope

Every assistant answer carries its tool-usage audit trail, so users can see
exactly which tools produced which numbers.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.core.dependencies import get_db, require_project_role, ProjectRole
from apps.api.modules.automl.evaluation import build_evaluation
from apps.api.modules.automl.models import Experiment
from apps.api.modules.conversational import models, schemas
from apps.api.modules.conversational.service import analyze_question
from apps.api.modules.datasets.models import Dataset, DatasetVersion
from apps.api.modules.datasets.quality import build_quality_report
from apps.api.modules.datasets.recommendations import build_recommendation
from apps.api.modules.projects.models import Project

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["AI Data Analyst"])


async def _latest_version_for_dataset(db: AsyncSession, project_id: uuid.UUID, dataset_id: uuid.UUID) -> DatasetVersion | None:
    stmt = (
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(
            DatasetVersion.dataset_id == dataset_id,
            Dataset.project_id == project_id,
        )
        .order_by(DatasetVersion.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _best_experiment_payload(db: AsyncSession, project_id: uuid.UUID) -> tuple[Experiment | None, dict | None, dict | None]:
    stmt = (
        select(Experiment)
        .where(Experiment.project_id == project_id)
        .options(selectinload(Experiment.trials))
        .order_by(Experiment.created_at.desc())
        .limit(1)
    )
    experiment = (await db.execute(stmt)).scalar_one_or_none()
    if not experiment:
        return None, None, None
    evaluation = build_evaluation(experiment)
    best_trial = next((t for t in experiment.trials if t.is_best), None)
    return experiment, evaluation, best_trial


async def _get_or_create_conversation(db: AsyncSession, project_id: uuid.UUID, dataset_id: uuid.UUID | None) -> models.Conversation:
    stmt = (
        select(models.Conversation)
        .where(models.Conversation.project_id == project_id)
    )
    if dataset_id is not None:
        stmt = stmt.where(models.Conversation.dataset_id == dataset_id)
    else:
        stmt = stmt.where(models.Conversation.dataset_id.is_(None))
    stmt = stmt.order_by(models.Conversation.created_at.desc()).limit(1)

    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if conversation is None:
        conversation = models.Conversation(project_id=project_id, dataset_id=dataset_id)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
    return conversation


@router.post("", response_model=schemas.ChatResponse)
async def send_chat_message(
    project_id: uuid.UUID,
    payload: schemas.ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Ask the AI Data Analyst a question. Numbers in the answer come only from
    executed tools; when no tool can answer, the assistant says so.
    """
    # ── Load context artifacts (all optional) ────────────────────────────────
    profile: dict | None = None
    quality_report: dict | None = None
    recommendation_plan: dict | None = None
    evaluation: dict | None = None
    global_explanation: dict | None = None

    version: DatasetVersion | None = None
    if payload.dataset_id is not None:
        version = await _latest_version_for_dataset(db, project_id, payload.dataset_id)
        if version is None:
            raise HTTPException(status_code=404, detail="No dataset version found for this dataset.")
        profile = version.profile_data or {}
        if "error" in profile:
            profile = None

    if profile:
        quality_report = build_quality_report(profile)
        recommendation_plan = await _build_plan_safe(profile)

    experiment, evaluation, best_trial = await _best_experiment_payload(db, project_id)

    if best_trial and best_trial.mlflow_run_id:
        try:
            from apps.api.modules.explainability import service as xai_service
            global_explanation = await xai_service.generate_global_shap(best_trial.id)
        except Exception:  # explanation is best-effort context for chat
            global_explanation = None

    context_payload = {
        "_quality_report": quality_report or {},
        "_recommendation_plan": recommendation_plan or {},
        "_evaluation": evaluation or {},
        "_global_explanation": global_explanation or {},
    }

    result = analyze_question(payload.message, profile, context_payload)

    # ── Persist conversation ─────────────────────────────────────────────────
    conversation = await _get_or_create_conversation(db, project_id, payload.dataset_id)
    db.add(models.ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    ))
    assistant_msg = models.ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        tools_used=result.get("tools_used") or [],
        generated_by=result.get("generated_by", "rules"),
    )
    db.add(assistant_msg)
    await db.commit()

    return schemas.ChatResponse(
        answer=result["answer"],
        tools_used=result.get("tools_used") or [],
        generated_by=result.get("generated_by", "rules"),
        conversation_id=conversation.id,
    )


@router.get("/history", response_model=schemas.ConversationHistoryOut)
async def get_history(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_role(ProjectRole.VIEWER)),
):
    stmt = select(models.Conversation).where(models.Conversation.project_id == project_id)
    if dataset_id is not None:
        stmt = stmt.where(models.Conversation.dataset_id == dataset_id)
    else:
        stmt = stmt.where(models.Conversation.dataset_id.is_(None))
    stmt = stmt.order_by(models.Conversation.created_at.desc()).limit(1).options(
        selectinload(models.Conversation.messages)
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if conversation is None:
        return schemas.ConversationHistoryOut(conversation_id=None, dataset_id=dataset_id, messages=[])

    return schemas.ConversationHistoryOut(
        conversation_id=conversation.id,
        dataset_id=conversation.dataset_id,
        messages=list(conversation.messages)[-limit:],
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    __editor=Depends(require_project_role(ProjectRole.EDITOR)),
):
    stmt = select(models.Conversation).where(models.Conversation.project_id == project_id)
    if dataset_id is not None:
        stmt = stmt.where(models.Conversation.dataset_id == dataset_id)
    else:
        stmt = stmt.where(models.Conversation.dataset_id.is_(None))
    conversations = (await db.execute(stmt)).scalars().all()
    for c in conversations:
        await db.delete(c)
    await db.commit()


async def _build_plan_safe(profile: dict) -> dict:
    try:
        return build_recommendation(profile)
    except Exception:  # noqa: BLE001 — chat must survive plan failures
        return {}
