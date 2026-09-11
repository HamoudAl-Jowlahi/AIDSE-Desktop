from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvaluationRunBase(BaseModel):
    provider: str = Field(..., description="AI provider to use (e.g., openai, gemini)")
    prompt_config_hash: Optional[str] = Field(None, description="Hash of the prompt used")


class EvaluationRunCreate(EvaluationRunBase):
    golden_dataset_id: UUID
    # Phase 13: how to grade outputs
    scoring_strategy: str = Field("semantic", description="exact | regex | semantic | llm_judge")
    scoring_params: Optional[Dict] = Field(default_factory=dict)
    # case_id → actual output. Required unless an evaluation provider is configured.
    actual_outputs: Optional[Dict[str, str]] = None


class EvaluationResultBase(BaseModel):
    actual_output: str
    score: float
    status: str
    scoring_detail: Optional[Dict] = None


class EvaluationResultResponse(EvaluationResultBase):
    id: UUID
    evaluation_run_id: UUID
    golden_case_id: UUID

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunResponse(EvaluationRunBase):
    id: UUID
    golden_dataset_id: UUID
    scoring_strategy: Optional[str] = None
    scoring_params: Optional[Dict] = None
    status: str
    aggregate_results: Optional[Dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: List[EvaluationResultResponse] = []

    model_config = ConfigDict(from_attributes=True)


# --- Phase 2: Regression Detection ---

class RegressionReportCaseResponse(BaseModel):
    golden_case_id: UUID
    category_tag: Optional[str]
    status_transition: str = Field(..., description="'Regressed', 'Newly Passing', or 'Stable'")
    baseline_score: Optional[float]
    new_score: float

    model_config = ConfigDict(from_attributes=True)


class RegressionReportResponse(BaseModel):
    evaluation_run_id: UUID
    baseline_run_id: UUID
    total_cases: int
    regressed_cases: int
    newly_passing_cases: int
    stable_cases: int
    critical_regressions: int
    cases: List[RegressionReportCaseResponse] = []

    model_config = ConfigDict(from_attributes=True)


# --- Phase 14: verdict + flaky detection (computed on read) ---

class FlakyCaseOut(BaseModel):
    golden_case_id: UUID
    category_tag: Optional[str] = None
    observed_statuses: List[str] = []
    note: str


class RegressionVerdictOut(RegressionReportResponse):
    verdict: str = Field(..., description="PASS | WARN | FAIL | NO_BASELINE")
    verdict_reason: str
    score_changed_cases: int = 0
    flaky_cases: List[FlakyCaseOut] = []


class ScheduledEvaluationCreate(BaseModel):
    golden_dataset_id: UUID
    provider: str
    cron_expression: str = Field(..., description="Standard cron expression for schedule")


class ScheduledEvaluationResponse(ScheduledEvaluationCreate):
    id: UUID
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
