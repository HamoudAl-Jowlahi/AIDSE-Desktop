import uuid
import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Boolean, Text, JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from apps.api.db.base import Base

class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    
    target_column = Column(String, nullable=False)
    problem_type = Column(String, nullable=False) # 'classification', 'regression'
    primary_metric = Column(String, nullable=False) # 'f1_macro', 'r2', 'rmse', etc.
    # Phase 8: user-selected focused model ids; NULL → task-appropriate defaults
    algorithms = Column(JSON, nullable=True)
    
    status = Column(String, nullable=False, default="pending") # 'pending', 'running', 'completed', 'failed'
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    project = relationship("Project", backref="experiments")
    dataset = relationship("Dataset", backref="experiments")
    trials = relationship("ModelTrial", back_populates="experiment", cascade="all, delete-orphan")


class ModelTrial(Base):
    __tablename__ = "model_trials"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    experiment_id = Column(Uuid, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    
    algorithm_name = Column(String, nullable=False) # 'random_forest', 'xgboost', 'lightgbm', 'catboost'
    hyperparameters = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    metrics = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    
    primary_metric_score = Column(Float, nullable=True) # Used for ranking
    mlflow_run_id = Column(String, nullable=True)
    is_best = Column(Boolean, default=False)
    
    status = Column(String, nullable=False, default="completed") # 'completed', 'failed', 'pruned'
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    experiment = relationship("Experiment", back_populates="trials")


from sqlalchemy import event


@event.listens_for(ModelTrial, "init")
def _sanitize_model_trial_init(target, args, kwargs):
    if "metrics" in kwargs and isinstance(kwargs["metrics"], dict):
        kwargs["metrics"] = {
            k: float(v)
            for k, v in kwargs["metrics"].items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }


@event.listens_for(ModelTrial, "load")
def _sanitize_model_trial_load(target, context):
    if hasattr(target, "metrics") and isinstance(target.metrics, dict):
        target.metrics = {
            k: float(v)
            for k, v in target.metrics.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }

