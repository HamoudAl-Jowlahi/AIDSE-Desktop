"""
AIDSE Platform — Reports Router (Phase 15)
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.dependencies import get_db, require_project_role, ProjectRole
from apps.api.modules.reporting.service import build_project_report

router = APIRouter(prefix="/projects/{project_id}/report", tags=["Reports"])


@router.get("")
async def get_project_report(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Coherent project report: dataset overview + quality totals,
    ML results with best models, AI evaluation status per golden dataset.
    """
    return await build_project_report(db, project_id)
