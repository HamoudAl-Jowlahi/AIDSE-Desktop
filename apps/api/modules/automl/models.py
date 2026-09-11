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


def json_safe_metrics(value):
    """
    Make a metrics value JSON-serializable without discarding structure.

    numpy scalars (np.float64, np.int64) are what the JSON encoder chokes on,
    so they are converted to their Python equivalents. Everything else keeps
    its shape.

    This replaces a filter that kept only top-level int/float entries. That
    filter silently deleted `confusion_matrix` and `per_class` — both nested
    dicts — on the way into the database and again on every load, so the
    confusion matrix and per-class breakdown could never be displayed. The
    unit test covering them passed anyway, because it used a plain FakeTrial
    that these listeners never touch.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)       # also strips numpy integer subclasses
    if isinstance(value, float):
        return float(value)     # np.float64 subclasses float
    if isinstance(value, dict):
        return {k: json_safe_metrics(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_metrics(v) for v in value]
    if isinstance(value, str) or value is None:
        return value
    # numpy scalars and 0-d arrays expose .item()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe_metrics(item())
        except (ValueError, TypeError):
            pass
    # ndarray and anything else list-like
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return json_safe_metrics(tolist())
        except (ValueError, TypeError):
            pass
    return value


@event.listens_for(ModelTrial, "init")
def _sanitize_model_trial_init(target, args, kwargs):
    """Coerce metrics to JSON-safe types at construction time."""
    if "metrics" in kwargs and isinstance(kwargs["metrics"], dict):
        kwargs["metrics"] = json_safe_metrics(kwargs["metrics"])


# There is deliberately no "load" listener. Rewriting target.metrics on load
# marks a freshly-loaded object dirty, which can provoke a pointless UPDATE on
# the next flush, and anything already stored came through the write path and
# is JSON-safe by construction.

