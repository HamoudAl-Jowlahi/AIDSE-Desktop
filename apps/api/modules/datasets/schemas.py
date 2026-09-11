from datetime import datetime  # noqa: F401  (kept for schema field types)
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetVersionBase(BaseModel):
    version_tag: str = Field(..., description="Semantic version or tag (e.g., 'v1.0.0', 'latest')")
    s3_key: str = Field(..., description="MinIO object path")


class DatasetVersionCreate(DatasetVersionBase):
    pass


class DatasetVersionResponse(DatasetVersionBase):
    id: UUID
    dataset_id: UUID
    profile_data: Optional[Dict] = None
    # pending → async profiling in progress; ready → profile available; failed → see profile_data["error"]
    profile_status: Optional[str] = None
    parent_version_id: Optional[UUID] = None
    transformation_history: Optional[List[Dict]] = None

    model_config = ConfigDict(from_attributes=True)


class TransformStep(BaseModel):
    action: str = Field(..., description="Action to perform: 'drop_column', 'fillna_mean', etc.")
    column: str = Field(..., description="Target column name")
    params: dict | None = Field(default_factory=dict, description="Additional parameters")


class TransformRequest(BaseModel):
    steps: list[TransformStep]


# --- Golden Case ---
class GoldenCaseBase(BaseModel):
    input_data: str
    expected_output: str
    category_tag: str | None = None

class GoldenCaseCreate(GoldenCaseBase):
    pass

class GoldenCaseResponse(GoldenCaseBase):
    id: UUID
    golden_dataset_id: UUID

    model_config = ConfigDict(from_attributes=True)

# --- Golden Dataset ---
class GoldenDatasetBase(BaseModel):
    name: str

class GoldenDatasetCreate(GoldenDatasetBase):
    version: int = 1

class GoldenDatasetResponse(GoldenDatasetBase):
    id: UUID
    project_id: UUID
    version: int
    baseline_run_id: UUID | None
    cases: list[GoldenCaseResponse] = []

    model_config = ConfigDict(from_attributes=True)


class DatasetBase(BaseModel):
    name: str = Field(..., description="Name of the dataset")
    description: str | None = Field(None, description="Optional description of the dataset contents")
    format: str = Field(..., description="Format of the dataset (e.g., 'json', 'csv')")


class DatasetCreate(DatasetBase):
    pass


class DatasetResponse(DatasetBase):
    id: UUID
    project_id: UUID
    versions: list[DatasetVersionResponse] = []

    model_config = ConfigDict(from_attributes=True)

class BaselineSetRequest(BaseModel):
    run_id: UUID


# --- Data Quality Center (Phase 3) ---
class QualityRecommendation(BaseModel):
    technique: str = Field(..., description="Recommended fix for the issue")
    alternatives: List[str] = Field(default_factory=list)
    reason: str = Field(..., description="Why this technique fits this problem")
    risk: str = Field(..., description="Trade-offs to be aware of")


class QualityIssueOut(BaseModel):
    id: str
    severity: str = Field(..., description="critical | warning | info")
    category: str = Field(..., description="missing_values | duplicates | outliers | ...")
    title: str
    columns: List[str] = Field(default_factory=list)
    affected_count: Optional[int] = None
    affected_pct: Optional[float] = None
    detection_method: str
    why_it_matters: str
    recommendation: QualityRecommendation


class QualitySummary(BaseModel):
    critical: int = 0
    warning: int = 0
    info: int = 0
    available: bool = True
    pending_profiling: Optional[bool] = None


class QualityReportOut(BaseModel):
    issues: List[QualityIssueOut]
    summary: QualitySummary


QualityIssueOut.model_rebuild()
QualityReportOut.model_rebuild()


# --- Outlier Intelligence (Phase 4) ---
class OutlierScanItem(BaseModel):
    column: str
    count: int
    share_pct: float
    lower_fence: Optional[float] = None
    upper_fence: Optional[float] = None
    recommendation: Dict


class OutlierScanOut(BaseModel):
    scanned_columns: int
    items: List[OutlierScanItem]


class OutlierMethodResult(BaseModel):
    method: str
    count: int
    params: Dict = Field(default_factory=dict)


class OutlierDetailOut(BaseModel):
    column: str
    num_rows: int
    methods: List[OutlierMethodResult]
    histogram: Optional[Dict] = None
    fences: Optional[Dict] = None
    recommendation: Dict


# --- Preparation Workbench (Phase 5) ---
class HistoryStepOut(BaseModel):
    step_no: int
    action: str
    column: Optional[str] = None
    params: Optional[Dict] = None
    note: Optional[str] = None


class PreviewOut(BaseModel):
    ok: bool
    error: Optional[str] = None
    truncated_for_preview: bool = False
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    applied_steps: List[HistoryStepOut]
    sample_before: List[Dict]
    sample_after: List[Dict]
    changed_columns: List[Dict]


class VersionHistoryEntry(BaseModel):
    version_id: UUID
    version_tag: str
    parent_version_id: Optional[UUID] = None
    steps: List[HistoryStepOut] = []


class CompareColumnChange(BaseModel):
    column: str
    change: str
    before: Optional[Any] = None
    after: Optional[Any] = None


class CompareOut(BaseModel):
    from_version_id: UUID
    to_version_id: UUID
    rows_before: int
    rows_after: int
    duplicate_rows_before: int
    duplicate_rows_after: int
    missing_cells_before: int
    missing_cells_after: int
    columns_added: List[str] = []
    columns_removed: List[str] = []
    columns_changed: List[CompareColumnChange] = []


# --- AI Recommendation Engine (Phase 6) ---
class PlanStep(BaseModel):
    order: int
    action: str = Field(..., description="Executable transform action name")
    column: Optional[str] = None
    params: Dict = Field(default_factory=dict)
    problem: str
    rationale: str
    expected_effect: str
    alternatives: List[str] = Field(default_factory=list)
    confidence: str = "medium"


class RecommendationOut(BaseModel):
    steps: List[PlanStep]
    notes: List[str] = Field(default_factory=list)
    stats_summary: Dict = Field(default_factory=dict)
    narrative: str
    generated_by: str = Field(..., description="rules | rules+llm")
    requires_approval: bool = True


RecommendationOut.model_rebuild()


# --- ML Task Detection (Phase 7) ---
class MetricRecommendation(BaseModel):
    metric: str
    primary: bool
    explanation: str


class ModelRecommendation(BaseModel):
    id: str
    name: str
    why: str


class SuggestedTarget(BaseModel):
    column: str
    task_type: str = "classification"
    confidence: str = "medium"
    reason: str
    rank: int = 1


class TaskDetectionOut(BaseModel):
    target_column: Optional[str] = None
    task_type: Optional[str] = Field(None, description="classification | regression | unsupervised")
    confidence: Optional[str] = None
    needs_confirmation: bool = False
    question: Optional[str] = None
    alternative_task: Optional[str] = None
    suggested_target: Optional[str] = None
    suggested_targets: List[SuggestedTarget] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    class_balance: Optional[Dict] = None
    recommended_metrics: List[MetricRecommendation] = Field(default_factory=list)
    recommended_models: List[ModelRecommendation] = Field(default_factory=list)


TaskDetectionOut.model_rebuild()


# --- Golden Dataset management (Phase 12) ---
class GoldenDatasetUpdate(BaseModel):
    name: Optional[str] = None
    version: Optional[int] = None


class GoldenCaseUpdate(BaseModel):
    input_data: Optional[str] = None
    expected_output: Optional[str] = None
    category_tag: Optional[str] = None


class BulkGoldenCasesRequest(BaseModel):
    cases: List[GoldenCaseCreate] = Field(default_factory=list)


BulkGoldenCasesRequest.model_rebuild()
