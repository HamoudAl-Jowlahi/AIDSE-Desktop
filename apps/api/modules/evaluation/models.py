import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base

if TYPE_CHECKING:
    from apps.api.modules.datasets.models import GoldenDataset, GoldenCase


class EvaluationRun(Base):
    """
    Tracks a single execution of an evaluation run against a GoldenDataset.
    """
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    golden_dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("golden_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_config_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Phase 13: how outputs were graded
    scoring_strategy: Mapped[str | None] = mapped_column(String(30), nullable=True)  # exact|regex|semantic|llm_judge
    scoring_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # pending, running, completed, failed
    aggregate_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    golden_dataset: Mapped["GoldenDataset"] = relationship("GoldenDataset")
    results: Mapped[list["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<EvaluationRun id={self.id} status={self.status!r}>"


class EvaluationResult(Base):
    """
    Stores the result of evaluating a single GoldenCase during an EvaluationRun.
    """
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    golden_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("golden_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actual_output: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False) # pass, fail, error
    scoring_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    run: Mapped["EvaluationRun"] = relationship("EvaluationRun", back_populates="results")
    golden_case: Mapped["GoldenCase"] = relationship("GoldenCase")

    def __repr__(self) -> str:
        return f"<EvaluationResult run={self.evaluation_run_id} score={self.score}>"


class RegressionReport(Base):
    """
    Stores the result of comparing an EvaluationRun against its baseline.
    """
    __tablename__ = "regression_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    baseline_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    total_cases: Mapped[int] = mapped_column(default=0)
    regressed_cases: Mapped[int] = mapped_column(default=0)
    newly_passing_cases: Mapped[int] = mapped_column(default=0)
    stable_cases: Mapped[int] = mapped_column(default=0)
    critical_regressions: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    run: Mapped["EvaluationRun"] = relationship("EvaluationRun", foreign_keys=[evaluation_run_id])
    baseline_run: Mapped["EvaluationRun"] = relationship("EvaluationRun", foreign_keys=[baseline_run_id])
    cases: Mapped[list["RegressionReportCase"]] = relationship(
        "RegressionReportCase", back_populates="report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RegressionReport run={self.evaluation_run_id} regressed={self.regressed_cases}>"


class RegressionReportCase(Base):
    """
    Stores the per-case diff for a RegressionReport.
    """
    __tablename__ = "regression_report_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("regression_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    golden_case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("golden_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status_transition: Mapped[str] = mapped_column(String(50), nullable=False) # 'Regressed', 'Newly Passing', 'Stable'
    baseline_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_score: Mapped[float] = mapped_column(Float, nullable=False)

    report: Mapped["RegressionReport"] = relationship("RegressionReport", back_populates="cases")
    golden_case: Mapped["GoldenCase"] = relationship("GoldenCase")

    def __repr__(self) -> str:
        return f"<RegressionReportCase case={self.golden_case_id} transition={self.status_transition}>"


class ScheduledEvaluation(Base):
    """
    Stores cron configuration for scheduled evaluation runs.
    """
    __tablename__ = "scheduled_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    golden_dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("golden_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    golden_dataset: Mapped["GoldenDataset"] = relationship("GoldenDataset")

    def __repr__(self) -> str:
        return f"<ScheduledEvaluation dataset={self.golden_dataset_id} cron={self.cron_expression}>"


