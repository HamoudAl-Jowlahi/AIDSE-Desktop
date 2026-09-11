import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class ModelTrialResponse(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    algorithm_name: str
    hyperparameters: Dict[str, Any]
    metrics: Dict[str, Any]
    primary_metric_score: Optional[float]
    mlflow_run_id: Optional[str]
    is_best: bool
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ExperimentCreate(BaseModel):
    target_column: str
    problem_type: str = Field(..., description="'classification' or 'regression'")
    primary_metric: str
    # Phase 8: focused model ids; omitted → task-appropriate defaults
    algorithms: Optional[List[str]] = None

class ExperimentResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    target_column: str
    problem_type: str
    primary_metric: str
    algorithms: Optional[List[str]] = None
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    trials: List[ModelTrialResponse] = []

    class Config:
        from_attributes = True


# --- Model Evaluation (Phase 9) ---
class MetricEvaluation(BaseModel):
    metric: str
    value: float
    explanation: str
    interpretation: str
    higher_is_better: bool = True
    is_primary: bool = False


class ConfusionMatrixOut(BaseModel):
    labels: List[str]
    matrix: List[List[int]]


class PerClassStat(BaseModel):
    class_name: str
    precision: float
    recall: float
    f1_score: float
    support: int


class TrialComparison(BaseModel):
    trial_id: uuid.UUID
    algorithm: str
    primary_score: Optional[float] = None
    is_best: bool = False


class EvaluationOut(BaseModel):
    experiment_id: uuid.UUID
    problem_type: str
    primary_metric: str
    target_column: str
    status: str
    trials_evaluated: int
    metrics: List[MetricEvaluation]
    confusion_matrix: Optional[ConfusionMatrixOut] = None
    confusion_matrix_reading_guide: Optional[str] = None
    per_class: Optional[List[PerClassStat]] = None
    trial_comparisons: List[TrialComparison] = []


EvaluationOut.model_rebuild()
