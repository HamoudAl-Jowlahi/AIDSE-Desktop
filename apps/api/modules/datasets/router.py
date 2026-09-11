import asyncio
import os
import shutil
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.core.dependencies import ProjectRole, get_current_user, get_db, require_project_role
from apps.api.core.storage import get_dataset_storage_dir
from apps.api.modules.projects.service import _write_audit_log
from apps.api.db.session import AsyncSessionLocal
from apps.api.modules.datasets import models, schemas
from apps.api.modules.datasets.ingestion import (
    INLINE_PROFILE_MAX_BYTES,
    FileValidationError,
    detect_format,
    load_dataframe,
    validate_upload_size,
)
from apps.api.modules.automl.task_detection import detect_task
from apps.api.modules.datasets.profiling import profile_dataset_file
from apps.api.modules.datasets.quality import build_quality_report
from apps.api.modules.datasets.recommendations import build_recommendation
from apps.api.modules.datasets.outliers import (
    SUPPORTED_METHODS,
    detect_outliers,
    recommend_treatment,
    scan_numeric_columns,
)
from apps.api.modules.datasets.transform import (
    TransformError,
    apply_transformations,
    preview_transformations,
)
import pandas as pd

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["Datasets"])

# Media types for downloads, keyed by on-disk extension (storage is normalized to CSV).
MEDIA_TYPES = {".csv": "text/csv"}


@router.post("", response_model=schemas.DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    project_id: uuid.UUID,
    dataset_in: schemas.DatasetCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Create a new dataset for a specific project.
    """
    dataset = models.Dataset(
        project_id=project_id,
        name=dataset_in.name,
        description=dataset_in.description,
        format=dataset_in.format,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)

    # We must explicitly eager load relationships if we are to return them in schemas that use them
    stmt = select(models.Dataset).options(selectinload(models.Dataset.versions)).where(models.Dataset.id == dataset.id)
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get("", response_model=list[schemas.DatasetResponse])
async def list_datasets(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    List all datasets in a project.
    """
    stmt = (
        select(models.Dataset)
        .options(selectinload(models.Dataset.versions))
        .where(models.Dataset.project_id == project_id)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/golden-datasets", response_model=schemas.GoldenDatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_golden_dataset(
    project_id: uuid.UUID,
    dataset_in: schemas.GoldenDatasetCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Create a new golden dataset for evaluation.
    """
    dataset = models.GoldenDataset(
        project_id=project_id,
        name=dataset_in.name,
        version=dataset_in.version,
    )
    db.add(dataset)
    await db.commit()

    # Re-fetch with cases eager-loaded so response serialization never
    # triggers a lazy load outside the greenlet (MissingGreenlet guard).
    stmt = (
        select(models.GoldenDataset)
        .options(selectinload(models.GoldenDataset.cases))
        .where(models.GoldenDataset.id == dataset.id)
    )
    return (await db.execute(stmt)).scalar_one()



@router.get("/golden-datasets", response_model=list[schemas.GoldenDatasetResponse])
async def list_golden_datasets(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    List all golden datasets in a project.
    """
    stmt = (
        select(models.GoldenDataset)
        .options(selectinload(models.GoldenDataset.cases))
        .where(models.GoldenDataset.project_id == project_id)
    )
    result = await db.execute(stmt)
    return result.scalars().all()




@router.get("/{dataset_id}", response_model=schemas.DatasetResponse)
async def get_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Get a single dataset and its versions.
    """
    stmt = (
        select(models.Dataset)
        .options(selectinload(models.Dataset.versions))
        .where(models.Dataset.id == dataset_id, models.Dataset.project_id == project_id)
    )
    result = await db.execute(stmt)
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return dataset


@router.post("/{dataset_id}/versions", response_model=schemas.DatasetVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_in: schemas.DatasetVersionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Add a new version to an existing dataset.
    """
    # Verify dataset belongs to project
    stmt = select(models.Dataset).where(models.Dataset.id == dataset_id, models.Dataset.project_id == project_id)
    result = await db.execute(stmt)
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found in this project")

    # Check if version tag already exists for this dataset
    stmt_check = select(models.DatasetVersion).where(
        models.DatasetVersion.dataset_id == dataset_id,
        models.DatasetVersion.version_tag == version_in.version_tag
    )
    check_res = await db.execute(stmt_check)
    if check_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version tag already exists for this dataset")

    dataset_version = models.DatasetVersion(
        dataset_id=dataset_id,
        version_tag=version_in.version_tag,
        s3_key=version_in.s3_key,
    )
    db.add(dataset_version)
    await db.commit()
    await db.refresh(dataset_version)

    return dataset_version


# --- Background profiling for large uploads ---

async def _profile_version_task(version_id: uuid.UUID, file_path: str) -> None:
    """
    Profile a large uploaded file off the request path, then persist the
    result with its own DB session. Runs via FastAPI BackgroundTasks.
    """
    profile = await asyncio.to_thread(profile_dataset_file, file_path)
    profile_status = "failed" if "error" in profile else "ready"
    async with AsyncSessionLocal() as session:
        stmt = select(models.DatasetVersion).where(models.DatasetVersion.id == version_id)
        version = (await session.execute(stmt)).scalar_one_or_none()
        if version is None:  # Deleted while profiling was running
            return
        version.profile_data = profile
        version.profile_status = profile_status
        await session.commit()


@router.post("/{dataset_id}/upload", response_model=schemas.DatasetVersionResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset_file(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Upload a dataset file (CSV/XLSX/XLS), validate it, normalize it to CSV
    storage, create a new DatasetVersion, and run profiling.

    Small files are profiled inline (off the event loop) so the response
    carries the full profile. Large files return immediately with
    profile_status="pending" and are profiled in a background task.
    """
    # 1. Validate extension + size before any parsing work
    try:
        fmt = detect_format(file.filename)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    raw = await file.read()
    try:
        validate_upload_size(raw)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. Verify dataset belongs to project
    stmt = select(models.Dataset).where(
        models.Dataset.id == dataset_id,
        models.Dataset.project_id == project_id
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in this project.")

    # 3. Save normalized CSV under canonical storage layout
    storage_dir = str(get_dataset_storage_dir(str(project_id)))
    os.makedirs(storage_dir, exist_ok=True)

    version_tag = f"v{uuid.uuid4().hex[:8]}"
    file_path = os.path.join(storage_dir, f"{dataset_id}_{version_tag}.csv")

    with open(file_path, "wb") as buffer:
        buffer.write(raw)

    # 4. Parse (thread-offloaded so the event loop stays responsive)
    try:
        df = await asyncio.to_thread(load_dataframe, file_path, fmt)
    except FileValidationError as exc:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(exc))

    # Always store the canonical CSV form (XLSX/XLS inputs get converted here)
    if fmt != ".csv":
        df.to_csv(file_path, index=False)

    # Keep the declared format accurate for the UI and downstream consumers
    dataset.format = fmt.lstrip(".")
    db.add(dataset)

    # 5. Profiling â€” inline for small files, background for large ones
    profile_status: str | None
    profile: dict | None

    if len(raw) <= INLINE_PROFILE_MAX_BYTES:
        profile = await asyncio.to_thread(profile_dataset_file, file_path)
        if "error" in profile:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=profile["error"])
        profile_status = "ready"
    else:
        profile = None
        profile_status = "pending"

    # 6. Create DatasetVersion
    dataset_version = models.DatasetVersion(
        dataset_id=dataset_id,
        version_tag=version_tag,
        s3_key=file_path,
        profile_data=profile,
        profile_status=profile_status,
    )
    db.add(dataset_version)
    await db.commit()
    await db.refresh(dataset_version)

    if profile_status == "pending":
        background_tasks.add_task(_profile_version_task, dataset_version.id, file_path)

    return dataset_version

@router.post("/{dataset_id}/versions/{version_id}/transform", response_model=schemas.DatasetVersionResponse, status_code=status.HTTP_201_CREATED)
async def transform_dataset_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    transform_req: schemas.TransformRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Apply a series of transformations to an existing dataset version and create a new version.
    """
    # 1. Find existing version
    stmt = (
        select(models.DatasetVersion)
        .join(models.Dataset)
        .where(
            models.DatasetVersion.id == version_id,
            models.DatasetVersion.dataset_id == dataset_id,
            models.Dataset.project_id == project_id
        )
    )
    source_version = (await db.execute(stmt)).scalar_one_or_none()

    if not source_version:
        raise HTTPException(status_code=404, detail="Source dataset version not found.")

    # 2. Setup output path
    storage_dir = str(get_dataset_storage_dir(str(project_id)))
    os.makedirs(storage_dir, exist_ok=True)

    new_version_tag = f"v{uuid.uuid4().hex[:8]}"
    output_path = os.path.join(storage_dir, f"{dataset_id}_{new_version_tag}.csv")

    # 3. Apply transformations
    steps_dict = [step.model_dump() for step in transform_req.steps]
    try:
        history = apply_transformations(source_version.s3_key, output_path, steps_dict)
    except TransformError as exc:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=400, detail=str(exc))

    # 4. Profile the new file
    profile = profile_dataset_file(output_path)
    if "error" in profile:
        os.remove(output_path)
        raise HTTPException(status_code=400, detail=f"Transformation produced an unreadable file: {profile['error']}")

    # 5. Create new version with full lineage
    new_dataset_version = models.DatasetVersion(
        dataset_id=dataset_id,
        version_tag=new_version_tag,
        s3_key=output_path,
        profile_data=profile,
        profile_status="ready",
        parent_version_id=source_version.id,
        transformation_history=history,
    )
    db.add(new_dataset_version)
    await db.commit()
    await db.refresh(new_dataset_version)

    return new_dataset_version

@router.get("/{dataset_id}/versions/{version_id}/quality", response_model=schemas.QualityReportOut)
async def get_version_quality_report(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Data Quality Center (Phase 3): derive structured issues â€” severity,
    affected columns, detection method, explanation and rule-based
    recommendation â€” from the stored profile of this dataset version.
    """
    stmt = (
        select(models.DatasetVersion)
        .join(models.Dataset)
        .where(
            models.DatasetVersion.id == version_id,
            models.DatasetVersion.dataset_id == dataset_id,
            models.Dataset.project_id == project_id
        )
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")

    if version.profile_status == "pending":
        return schemas.QualityReportOut(issues=[], summary={
            "critical": 0, "warning": 0, "info": 0,
            "available": False, "pending_profiling": True,
        })

    return build_quality_report(version.profile_data or {})


@router.get("/{dataset_id}/versions/{version_id}/download", response_class=FileResponse)
async def download_dataset_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Download the physical CSV file for a dataset version.
    """
    stmt = (
        select(models.DatasetVersion)
        .join(models.Dataset)
        .where(
            models.DatasetVersion.id == version_id,
            models.DatasetVersion.dataset_id == dataset_id,
            models.Dataset.project_id == project_id
        )
    )
    version = (await db.execute(stmt)).scalar_one_or_none()

    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")

    if not os.path.exists(version.s3_key):
        raise HTTPException(status_code=404, detail="Physical file not found on disk.")

    # Return the file as a downloadable attachment (storage is normalized to CSV)
    filename = os.path.basename(version.s3_key)
    ext = os.path.splitext(filename)[1].lower()
    return FileResponse(path=version.s3_key, filename=filename, media_type=MEDIA_TYPES.get(ext, "application/octet-stream"))

# --- Golden Datasets: scoped operations ---

@router.post("/golden-datasets/{golden_dataset_id}/baseline", response_model=schemas.GoldenDatasetResponse, status_code=status.HTTP_200_OK)
async def set_golden_dataset_baseline(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    payload: schemas.BaselineSetRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """Set the baseline evaluation run for a golden dataset."""
    stmt = (
        select(models.GoldenDataset)
        .options(selectinload(models.GoldenDataset.cases))
        .where(
            models.GoldenDataset.id == golden_dataset_id,
            models.GoldenDataset.project_id == project_id,
        )
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden Dataset not found in this project")

    dataset.baseline_run_id = payload.run_id
    await db.commit()

    stmt = (
        select(models.GoldenDataset)
        .options(selectinload(models.GoldenDataset.cases))
        .where(
            models.GoldenDataset.id == golden_dataset_id,
            models.GoldenDataset.project_id == project_id,
        )
    )
    return (await db.execute(stmt)).scalar_one()


@router.post("/golden-datasets/{golden_dataset_id}/cases", response_model=schemas.GoldenCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_golden_case(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    case_in: schemas.GoldenCaseCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """Add a single case to a golden dataset."""
    stmt = select(models.GoldenDataset).where(
        models.GoldenDataset.id == golden_dataset_id,
        models.GoldenDataset.project_id == project_id,
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden Dataset not found in this project")

    golden_case = models.GoldenCase(
        golden_dataset_id=golden_dataset_id,
        input_data=case_in.input_data,
        expected_output=case_in.expected_output,
        category_tag=case_in.category_tag,
    )
    db.add(golden_case)
    await db.commit()
    await db.refresh(golden_case)
    return golden_case



@router.patch("/golden-datasets/{golden_dataset_id}", response_model=schemas.GoldenDatasetResponse)
async def update_golden_dataset(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    update_in: schemas.GoldenDatasetUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """Rename a golden dataset and/or bump its version."""
    stmt = (
        select(models.GoldenDataset)
        .options(selectinload(models.GoldenDataset.cases))
        .where(models.GoldenDataset.id == golden_dataset_id, models.GoldenDataset.project_id == project_id)
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden Dataset not found in this project")

    if update_in.name is not None:
        dataset.name = update_in.name
    if update_in.version is not None:
        dataset.version = update_in.version
    await db.commit()
    await db.refresh(dataset)
    return dataset


@router.delete("/golden-datasets/{golden_dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_golden_dataset(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    stmt = select(models.GoldenDataset).where(
        models.GoldenDataset.id == golden_dataset_id, models.GoldenDataset.project_id == project_id
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden Dataset not found in this project")
    await db.delete(dataset)
    await db.commit()


@router.post("/golden-datasets/{golden_dataset_id}/cases/bulk", response_model=list[schemas.GoldenCaseResponse], status_code=status.HTTP_201_CREATED)
async def bulk_create_golden_cases(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    payload: schemas.BulkGoldenCasesRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Import many cases at once (paste from CSV/JSON exports).
    Invalid rows are rejected as a whole so partial imports never happen.
    """
    stmt = select(models.GoldenDataset).where(
        models.GoldenDataset.id == golden_dataset_id, models.GoldenDataset.project_id == project_id
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden Dataset not found in this project")
    if not payload.cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No cases supplied.")

    created = [
        models.GoldenCase(
            golden_dataset_id=golden_dataset_id,
            input_data=c.input_data,
            expected_output=c.expected_output,
            category_tag=c.category_tag,
        )
        for c in payload.cases
    ]
    db.add_all(created)
    await db.commit()
    for c in created:
        await db.refresh(c)
    return created


@router.patch("/golden-datasets/{golden_dataset_id}/cases/{case_id}", response_model=schemas.GoldenCaseResponse)
async def update_golden_case(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    case_id: uuid.UUID,
    case_in: schemas.GoldenCaseUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """Edit one case's input / expected output / tag."""
    stmt = (
        select(models.GoldenCase)
        .join(models.GoldenDataset)
        .where(
            models.GoldenCase.id == case_id,
            models.GoldenCase.golden_dataset_id == golden_dataset_id,
            models.GoldenDataset.project_id == project_id,
        )
    )
    case = (await db.execute(stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden case not found.")

    if case_in.input_data is not None:
        case.input_data = case_in.input_data
    if case_in.expected_output is not None:
        case.expected_output = case_in.expected_output
    if case_in.category_tag is not None:
        case.category_tag = case_in.category_tag
    await db.commit()
    await db.refresh(case)
    return case


@router.delete("/golden-datasets/{golden_dataset_id}/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_golden_case(
    project_id: uuid.UUID,
    golden_dataset_id: uuid.UUID,
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    stmt = (
        select(models.GoldenCase)
        .join(models.GoldenDataset)
        .where(
            models.GoldenCase.id == case_id,
            models.GoldenCase.golden_dataset_id == golden_dataset_id,
            models.GoldenDataset.project_id == project_id,
        )
    )
    case = (await db.execute(stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden case not found.")
    await db.delete(case)
    await db.commit()


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Delete a dataset, all its versions (DB cascade) and the stored files.
    Phase 17: audited as a destructive action.
    """
    stmt = (
        select(models.Dataset)
        .options(selectinload(models.Dataset.versions))
        .where(models.Dataset.id == dataset_id, models.Dataset.project_id == project_id)
    )
    dataset = (await db.execute(stmt)).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found in this project.")

    # Best-effort physical cleanup (files may already be gone)
    removed = 0
    for version in dataset.versions:
        try:
            if version.s3_key and os.path.exists(version.s3_key):
                os.remove(version.s3_key)
                removed += 1
        except OSError:
            logger.warning("Could not remove file %s", version.s3_key)

    await db.delete(dataset)
    await _write_audit_log(
        db,
        project_id=project_id,
        actor_id=current_user.id,
        action="dataset.deleted",
        target_type="dataset",
        target_id=dataset_id,
        metadata={"name": dataset.name, "files_removed": removed},
    )
    await db.commit()


# --- Outlier Intelligence (Phase 4) ---

def _load_version_dataframe(version: models.DatasetVersion) -> pd.DataFrame:
    if not os.path.exists(version.s3_key):
        raise HTTPException(status_code=404, detail="Physical file not found on disk.")
    try:
        return pd.read_csv(version.s3_key)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Stored file is unreadable: {exc}")


async def _get_version_or_404(
    project_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID, db: AsyncSession
) -> models.DatasetVersion:
    stmt = (
        select(models.DatasetVersion)
        .join(models.Dataset)
        .where(
            models.DatasetVersion.id == version_id,
            models.DatasetVersion.dataset_id == dataset_id,
            models.Dataset.project_id == project_id,
        )
    )
    version = (await db.execute(stmt)).scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    return version


@router.get("/{dataset_id}/versions/{version_id}/outliers", response_model=schemas.OutlierScanOut)
async def scan_outliers(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    ml_task: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Quick IQR scan of every numeric column with per-column treatment
    recommendations. Detection is advisory â€” nothing is modified.
    """
    version = await _get_version_or_404(project_id, dataset_id, version_id, db)
    df = await asyncio.to_thread(_load_version_dataframe, version)
    items = await asyncio.to_thread(scan_numeric_columns, df, ml_task)
    return schemas.OutlierScanOut(scanned_columns=len(items), items=items)


@router.get("/{dataset_id}/versions/{version_id}/outliers/detail", response_model=schemas.OutlierDetailOut)
async def outlier_column_detail(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    column: str,
    method: str = "iqr",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Deep-dive one column: counts for the chosen method (or all methods when
    method=all), the stored distribution histogram and a treatment
    recommendation that weighs skew, share and ML task.
    """
    if method != "all" and method not in SUPPORTED_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown method '{method}'. Supported: iqr, zscore, isolation_forest, lof, all.",
        )

    version = await _get_version_or_404(project_id, dataset_id, version_id, db)
    df = await asyncio.to_thread(_load_version_dataframe, version)

    if column not in df.columns:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found.")
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise HTTPException(status_code=400, detail=f"Column '{column}' is not numeric.")

    methods_to_run = list(SUPPORTED_METHODS) if method == "all" else [method]

    def run() -> dict:
        series = df[column]
        clean = series.dropna()
        results = [detect_outliers(series, m) for m in methods_to_run]
        col_stats = {
            "_num_rows": int(len(clean)),
            "skew": float(clean.skew()) if len(clean) > 2 else None,
            "unique_count": int(clean.nunique()),
        }
        primary = results[0]
        hist = None
        profile_cols = (version.profile_data or {}).get("columns", {})
        if column in profile_cols:
            hist = profile_cols[column].get("histogram")
            if "skew" in profile_cols[column]:
                col_stats["skew"] = profile_cols[column]["skew"]
        return {
            "column": column,
            "num_rows": int(len(clean)),
            "methods": [
                schemas.OutlierMethodResult(
                    method=r["method"], count=r["count"], params=r.get("params") or {}
                )
                for r in results
            ],
            "histogram": hist,
            "fences": primary.get("params"),
            "recommendation": recommend_treatment(col_stats, primary),
        }

    return await asyncio.to_thread(run)


# --- AI Recommendation Engine (Phase 6) ---

@router.get("/{dataset_id}/versions/{version_id}/recommendations", response_model=schemas.RecommendationOut)
async def get_recommendations(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Hybrid AI preprocessing plan: the rule/statistical engine inspects the
    stored profile and emits an ordered executable plan; an optional LLM
    layer narrates it. Nothing is applied automatically â€” steps must be
    queued and approved in the workbench.
    """
    version = await _get_version_or_404(project_id, dataset_id, version_id, db)

    if not version.profile_data or "error" in (version.profile_data or {}):
        raise HTTPException(
            status_code=400,
            detail="Recommendations need a completed profile for this version.",
        )

    return await asyncio.to_thread(build_recommendation, version.profile_data)


# --- ML Task Detection (Phase 7) ---

@router.get("/{dataset_id}/versions/{version_id}/task-detection", response_model=schemas.TaskDetectionOut)
async def detect_ml_task(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    target_column: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Decide classification vs regression vs unsupervised for a chosen target.
    Honest by design: ambiguous numeric targets return needs_confirmation
    with a question instead of silently guessing the user's objective.
    Includes metric + focused-model recommendations (Phases 7-8).
    """
    version = await _get_version_or_404(project_id, dataset_id, version_id, db)
    profile = version.profile_data or {}
    if not profile or "error" in profile:
        raise HTTPException(status_code=400, detail="Task detection needs a completed profile for this version.")
    return await asyncio.to_thread(detect_task, profile, target_column)


# --- Preparation Workbench endpoints (Phase 5) ---

@router.post("/{dataset_id}/versions/{version_id}/preview-transform", response_model=schemas.PreviewOut)
async def preview_transform(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    transform_req: schemas.TransformRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Dry-run the given steps against the version file and return
    before/after samples plus a change summary. Nothing is persisted.
    """
    version = await _get_version_or_404(project_id, dataset_id, version_id, db)
    steps_dict = [step.model_dump() for step in transform_req.steps]
    try:
        return await asyncio.to_thread(
            preview_transformations, version.s3_key, steps_dict
        )
    except TransformError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{dataset_id}/versions/{version_id}/history", response_model=list[schemas.VersionHistoryEntry])
async def get_version_history(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Walk the parent chain from this version back to the original upload.
    Returns oldest-first so the UI renders 'Step 1 â€¦ Step N' naturally.
    """
    version = await _get_version_or_404(project_id, dataset_id, version_id, db)

    chain: List[models.DatasetVersion] = []
    cursor: models.DatasetVersion | None = version
    seen: set[uuid.UUID] = set()
    while cursor is not None and cursor.id not in seen:
        seen.add(cursor.id)
        chain.append(cursor)
        if cursor.parent_version_id is None:
            break
        stmt = select(models.DatasetVersion).where(
            models.DatasetVersion.id == cursor.parent_version_id,
            models.DatasetVersion.dataset_id == dataset_id,
        )
        cursor = (await db.execute(stmt)).scalar_one_or_none()

    chain.reverse()  # original upload first
    return [
        schemas.VersionHistoryEntry(
            version_id=v.id,
            version_tag=v.version_tag,
            parent_version_id=v.parent_version_id,
            steps=v.transformation_history or [],
        )
        for v in chain
    ]


@router.post("/{dataset_id}/versions/{version_id}/revert", response_model=schemas.DatasetVersionResponse, status_code=status.HTTP_201_CREATED)
async def revert_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.EDITOR)),
):
    """
    Undo by lineage: create a NEW version whose contents equal the parent of
    the given version (original uploads have no parent â†’ nothing to undo).
    The reverted-from version stays intact; no data is ever destroyed.
    """
    version = await _get_version_or_404(project_id, dataset_id, version_id, db)

    if version.parent_version_id is None:
        raise HTTPException(
            status_code=400,
            detail="This is an original upload â€” nothing to undo.",
        )

    parent_stmt = select(models.DatasetVersion).where(
        models.DatasetVersion.id == version.parent_version_id,
        models.DatasetVersion.dataset_id == dataset_id,
    )
    parent = (await db.execute(parent_stmt)).scalar_one_or_none()
    if parent is None or not os.path.exists(parent.s3_key):
        raise HTTPException(status_code=404, detail="Parent version file no longer exists.")

    storage_dir = str(get_dataset_storage_dir(str(project_id)))
    os.makedirs(storage_dir, exist_ok=True)
    new_tag = f"v{uuid.uuid4().hex[:8]}"
    output_path = os.path.join(storage_dir, f"{dataset_id}_{new_tag}.csv")
    shutil.copyfile(parent.s3_key, output_path)

    revert_step = [{
        "step_no": 1,
        "action": "revert",
        "column": None,
        "params": {"reverted_from": version.version_tag, "restored_from": parent.version_tag},
        "note": f"Reverted '{version.version_tag}' back to state of '{parent.version_tag}'",
    }]
    profile = await asyncio.to_thread(profile_dataset_file, output_path)
    new_version = models.DatasetVersion(
        dataset_id=dataset_id,
        version_tag=new_tag,
        s3_key=output_path,
        profile_data=profile,
        profile_status="failed" if "error" in profile else "ready",
        parent_version_id=parent.id,
        transformation_history=revert_step,
    )
    db.add(new_version)
    await db.commit()
    await db.refresh(new_version)
    return new_version


@router.get("/{dataset_id}/compare", response_model=schemas.CompareOut)
async def compare_versions(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    from_version: uuid.UUID,
    to_version: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_project_role(ProjectRole.VIEWER)),
):
    """
    Before/after comparison between two versions using their stored profiles
    (row counts, duplicates, missing cells, added/removed/changed columns).
    """
    async def load(v_id: uuid.UUID) -> models.DatasetVersion:
        stmt = (
            select(models.DatasetVersion)
            .join(models.Dataset)
            .where(
                models.DatasetVersion.id == v_id,
                models.DatasetVersion.dataset_id == dataset_id,
                models.Dataset.project_id == project_id,
            )
        )
        v = (await db.execute(stmt)).scalar_one_or_none()
        if not v:
            raise HTTPException(status_code=404, detail="One of the compared versions was not found.")
        return v

    base, target = await load(from_version), await load(to_version)
    p_before: dict = base.profile_data or {}
    p_after: dict = target.profile_data or {}
    if "error" in p_before or "error" in p_after or not p_before or not p_after:
        raise HTTPException(status_code=400, detail="Both versions need a completed profile to compare.")

    cols_b: dict = p_before.get("columns", {})
    cols_a: dict = p_after.get("columns", {})

    def missing_cells(cols: dict) -> int:
        return sum(int(s.get("null_count") or 0) for s in cols.values())

    changed: list[schemas.CompareColumnChange] = []
    for c in sorted(set(cols_b) & set(cols_a)):
        sb, sa = cols_b[c], cols_a[c]
        if sb.get("type") != sa.get("type"):
            changed.append(schemas.CompareColumnChange(column=c, change="dtype", before=sb.get("type"), after=sa.get("type")))
        elif (sb.get("null_count") or 0) != (sa.get("null_count") or 0):
            changed.append(schemas.CompareColumnChange(column=c, change="nulls", before=sb.get("null_count"), after=sa.get("null_count")))

    return schemas.CompareOut(
        from_version_id=base.id,
        to_version_id=target.id,
        rows_before=int(p_before.get("num_rows") or 0),
        rows_after=int(p_after.get("num_rows") or 0),
        duplicate_rows_before=int(p_before.get("duplicate_rows") or 0),
        duplicate_rows_after=int(p_after.get("duplicate_rows") or 0),
        missing_cells_before=missing_cells(cols_b),
        missing_cells_after=missing_cells(cols_a),
        columns_added=[c for c in cols_a if c not in cols_b],
        columns_removed=[c for c in cols_b if c not in cols_a],
        columns_changed=changed,
    )
