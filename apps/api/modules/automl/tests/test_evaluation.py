"""
AIDSE Platform — Model Evaluation + Explainable AI Tests (Phases 9-10)

Covers:
- Evaluation builder: interpretations, confusion matrix, per-class,
  trial ranking for both metric directions
- compute_metrics regression includes MSE; classification shape intact
- preprocess_data exposes target class names
- Evaluation endpoint wiring
- Explainability strategy selection + linear local contribution math
"""
from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
import pytest
from httpx import AsyncClient

from apps.api.modules.automl.evaluation import build_evaluation, interpret
from apps.api.modules.automl.service import (
    compute_metrics,
    preprocess_data,
    get_model,
)
from apps.api.modules.explainability.service import _method_for
from apps.api.modules.automl.models import Experiment, ModelTrial

from apps.api.modules.datasets.tests.test_ingestion import create_dataset, create_project


# ──────────────────────────────────────────────────────────────────────────────
# Phase 9 — interpretation sentences
# ──────────────────────────────────────────────────────────────────────────────

def test_recall_interpretation_matches_spec_example():
    text = interpret("recall", 0.91)
    assert "91%" in text and "detected" in text.lower()


def test_accuracy_interpretation():
    assert "85%" in interpret("accuracy", 0.85)


def test_r2_interpretation_mentions_variance():
    assert "variance" in interpret("r2", 0.77).lower()


def test_rmse_interpretation_mentions_units():
    assert "units" in interpret("rmse", 12.4).lower()


def test_every_core_metric_has_explanation_and_interpretation():
    from apps.api.modules.automl.task_detection import METRIC_EXPLANATIONS
    for m in ("accuracy", "f1_macro", "precision", "recall", "roc_auc", "r2", "rmse", "mae"):
        assert len(METRIC_EXPLANATIONS[m]) > 15
        assert len(interpret(m, 0.8)) > 10


# ──────────────────────────────────────────────────────────────────────────────
# Phase 9 — evaluation builder on synthetic experiment rows
# ──────────────────────────────────────────────────────────────────────────────

class FakeTrial:
    def __init__(self, algo, score, metrics, is_best=False):
        self.id = uuid.uuid4()
        self.algorithm_name = algo
        self.primary_metric_score = score
        self.metrics = metrics
        self.is_best = is_best
        self.status = "completed"


class FakeExperiment:
    def __init__(self, trials, problem="classification", metric="f1_macro"):
        self.id = uuid.uuid4()
        self.trials = trials
        self.problem_type = problem
        self.primary_metric = metric
        self.target_column = "target"
        self.status = "completed"


CLASSIFICATION_METRICS = {
    "accuracy": 0.88, "f1_macro": 0.84, "precision": 0.86, "recall": 0.82,
    "roc_auc": 0.93,
    "confusion_matrix": {
        "labels": ["no", "yes"],
        "matrix": [[70, 5], [7, 18]],
    },
    "per_class": {
        "no": {"precision": 0.91, "recall": 0.93, "f1_score": 0.92, "support": 75},
        "yes": {"precision": 0.78, "recall": 0.72, "f1_score": 0.75, "support": 25},
    },
}


def test_evaluation_surfaces_confusion_matrix_and_per_class():
    trials = [
        FakeTrial("random_forest", 0.79, CLASSIFICATION_METRICS),
        FakeTrial("logistic_regression", 0.84, CLASSIFICATION_METRICS),
    ]
    result = build_evaluation(FakeExperiment(trials))

    assert result["trials_evaluated"] == 2
    assert result["confusion_matrix"]["labels"] == ["no", "yes"]
    assert result["confusion_matrix"]["matrix"] == [[70, 5], [7, 18]]
    assert "bottom-left" in result["confusion_matrix_reading_guide"]
    per_class_names = {c["class_name"] for c in result["per_class"]}
    assert per_class_names == {"no", "yes"}

    # Best trial ranked by primary metric (higher better)
    assert result["trial_comparisons"][0]["algorithm"] == "logistic_regression"

    metrics_by_name = {m["metric"]: m for m in result["metrics"]}
    assert metrics_by_name["f1_macro"]["is_primary"] is True
    assert metrics_by_name["recall"]["interpretation"]
    assert metrics_by_name["recall"]["explanation"]


def test_regression_ranking_prefers_lower_rmse():
    trials = [
        FakeTrial("xgboost", 3.1, {"r2": 0.6, "rmse": 3.1, "mae": 2.1, "mse": 9.6}),
        FakeTrial("linear_regression", 2.4, {"r2": 0.7, "rmse": 2.4, "mae": 1.8, "mse": 5.8}),
    ]
    result = build_evaluation(FakeExperiment(trials, problem="regression", metric="rmse"))
    assert result["trial_comparisons"][0]["algorithm"] == "linear_regression"
    names = {m["metric"] for m in result["metrics"]}
    assert {"r2", "rmse", "mae", "mse"} <= names


def test_empty_experiment_handled():
    result = build_evaluation(FakeExperiment([]))
    assert result["metrics"] == [] and result["status"] == "completed"


# ──────────────────────────────────────────────────────────────────────────────
# Training plumbing
# ──────────────────────────────────────────────────────────────────────────────

def test_compute_metrics_regression_includes_mse():
    rng = np.random.default_rng(3)
    y = rng.normal(50, 10, 100)
    preds = y + 1.0
    m = compute_metrics(y, preds, "regression")
    assert "mse" in m and m["mse"] == pytest.approx(m["rmse"] ** 2, rel=1e-6)


def test_preprocess_returns_class_names_for_string_target():
    df = pd.DataFrame({
        "num": [1.0, 2.0, 3.0, 4.0],
        "label": ["cat", "dog", "cat", "dog"],
    })
    X, y, classes = preprocess_data(df, "label", "classification")
    assert classes == ["cat", "dog"]
    assert set(y) == {0, 1}


def test_preprocess_numeric_target_reports_encoded_labels():
    df = pd.DataFrame({"num": [1.0, 2.0, 3.0, 4.0], "target": [0, 1, 0, 1]})
    X, y, classes = preprocess_data(df, "target", "classification")
    assert classes == ["0", "1"]


# ──────────────────────────────────────────────────────────────────────────────
# Phase 10 — explainability strategy selection
# ──────────────────────────────────────────────────────────────────────────────

def test_strategy_tree_models_use_shap_tree():
    assert _method_for("random_forest", None) == "shap_tree"
    assert _method_for("xgboost", None) == "shap_tree"


def test_strategy_linear_models_detected_by_coef():
    model = get_model("logistic_regression", "classification", {})
    assert _method_for("logistic_regression", model) == "coefficients"
    reg = get_model("linear_regression", "regression", {})
    assert _method_for("linear_regression", reg) == "coefficients"


def test_strategy_svm_falls_back_to_kernel():
    svm = get_model("svm", "classification", {})
    assert _method_for("svm", svm) == "kernel_shap"


def test_linear_local_contributions_are_exact_math():
    """coefficient × (value − mean) must equal a hand-computed contribution."""
    model = get_model("linear_regression", "regression", {})
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [10., 20., 30., 40., 50.]})
    y = pd.Series([2 * x + 1 for x in X["a"]])
    model.fit(X, y)

    row = X.iloc[[0]]
    contrib_a = float(model.coef_[0]) * (row["a"].iloc[0] - X["a"].mean())
    assert contrib_a == pytest.approx(-2 * float(model.coef_[0]), rel=1e-6)


@pytest.mark.asyncio
async def test_evaluation_endpoint(client: AsyncClient, auth_headers: dict, db):
    """Endpoint returns explained evaluation for a seeded experiment."""
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])

    exp_id = uuid.uuid4()
    experiment = Experiment(
        id=exp_id,
        project_id=uuid.UUID(project["id"]),
        dataset_id=uuid.UUID(dataset["id"]),
        target_column="target",
        problem_type="classification",
        primary_metric="f1_macro",
        status="completed",
    )
    trial = ModelTrial(
        experiment_id=exp_id,
        algorithm_name="logistic_regression",
        hyperparameters={},
        metrics=dict(CLASSIFICATION_METRICS),
        primary_metric_score=0.84,
        is_best=True,
        status="completed",
    )
    db.add_all([experiment, trial])
    await db.commit()

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/automl/experiments/{exp_id}/evaluation",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["problem_type"] == "classification"
    assert body["confusion_matrix"]["matrix"] == [[70, 5], [7, 18]]
    recall = next(m for m in body["metrics"] if m["metric"] == "recall")
    assert "%" in recall["interpretation"]
    assert len(body["per_class"]) == 2


# ── Regression: nested evaluation artifacts must survive persistence ────────
#
# The tests above build trials from FakeTrial, a plain class, so the SQLAlchemy
# listeners on ModelTrial never run against them. Those listeners used to keep
# only top-level int/float entries, which deleted confusion_matrix and
# per_class on write and again on load — the confusion matrix could never
# reach the UI, and nothing failed. These use the real mapped class.


def test_model_trial_keeps_nested_artifacts_at_construction():
    """The init listener must coerce types without dropping structure."""
    trial = ModelTrial(
        experiment_id=uuid.uuid4(),
        algorithm_name="logistic_regression",
        hyperparameters={},
        metrics=dict(CLASSIFICATION_METRICS),
        primary_metric_score=0.84,
        status="completed",
    )

    assert trial.metrics["confusion_matrix"]["matrix"] == [[70, 5], [7, 18]]
    assert trial.metrics["confusion_matrix"]["labels"] == ["no", "yes"]
    assert set(trial.metrics["per_class"]) == {"no", "yes"}
    assert trial.metrics["accuracy"] == 0.88


def test_numpy_values_are_coerced_but_nesting_is_kept():
    """
    Coercion exists because numpy scalars are not JSON-serializable. It must
    reach inside nested structures rather than deleting them.
    """
    import json

    import numpy as np

    trial = ModelTrial(
        experiment_id=uuid.uuid4(),
        algorithm_name="random_forest",
        hyperparameters={},
        metrics={
            "accuracy": np.float64(0.91),
            "confusion_matrix": {"labels": ["a", "b"], "matrix": np.array([[8, 1], [2, 9]])},
            "per_class": {"a": {"support": np.int64(9)}},
        },
        primary_metric_score=0.91,
        status="completed",
    )

    # Serializable is the whole point of the coercion.
    json.dumps(trial.metrics)

    assert trial.metrics["accuracy"] == pytest.approx(0.91)
    assert trial.metrics["confusion_matrix"]["matrix"] == [[8, 1], [2, 9]]
    assert trial.metrics["per_class"]["a"]["support"] == 9


@pytest.mark.asyncio
async def test_nested_artifacts_survive_a_database_round_trip(db):
    """
    Write a trial, expire it from the session, read it back. A "load" listener
    that rewrote metrics would strip the artifacts here.
    """
    exp_id = uuid.uuid4()
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()

    db.add(Experiment(
        id=exp_id,
        project_id=project_id,
        dataset_id=dataset_id,
        target_column="target",
        problem_type="classification",
        primary_metric="f1_macro",
        status="completed",
    ))
    db.add(ModelTrial(
        experiment_id=exp_id,
        algorithm_name="logistic_regression",
        hyperparameters={},
        metrics=dict(CLASSIFICATION_METRICS),
        primary_metric_score=0.84,
        is_best=True,
        status="completed",
    ))
    await db.commit()
    db.expire_all()

    from sqlalchemy import select

    reloaded = (await db.execute(
        select(ModelTrial).where(ModelTrial.experiment_id == exp_id)
    )).scalar_one()

    assert reloaded.metrics["confusion_matrix"]["matrix"] == [[70, 5], [7, 18]], (
        "confusion_matrix did not survive the round trip"
    )
    assert reloaded.metrics["per_class"]["yes"]["support"] == 25
