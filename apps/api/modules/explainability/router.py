import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from apps.api.core.dependencies import require_project_role, ProjectRole
from apps.api.modules.explainability import schemas, service

router = APIRouter(prefix="/projects/{project_id}/automl/trials/{trial_id}/explain", tags=["Explainability"])

@router.get("/global", response_model=schemas.ShapGlobalResponse)
async def get_global_explanation(
    project_id: uuid.UUID,
    trial_id: uuid.UUID,
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Generate a global SHAP summary plot and feature importances for a trained model.
    """
    try:
        result = await service.generate_global_shap(trial_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate SHAP global summary: {str(e)}")

@router.get("/local", response_model=schemas.ShapLocalResponse)
async def get_local_explanation(
    project_id: uuid.UUID,
    trial_id: uuid.UUID,
    row_index: int = 0,
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Generate a local SHAP explanation (force/waterfall plot) for a specific row index.
    """
    try:
        result = await service.generate_local_shap(trial_id, row_index)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate SHAP local summary: {str(e)}")
