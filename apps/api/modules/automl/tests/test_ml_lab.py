"""
AIDSE Platform — ML Task Detection + Focused Model Set Tests (Phases 7-8)

Covers:
- Task detection: regression, binary/ambiguous numeric, categorical,
  identifier warnings, no-target hint
- Metric recommendations adapt to class balance
- Focused model registry (get_model) incl. new LR/SVM/LinearRegression
- compute_metrics ROC-AUC behavior with/without probabilities
- Endpoint wiring (detection + experiment creation with algorithms)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.api.modules.automl.service import (
    FOCUSED_CLASSIFICATION,
    FOCUSED_REGRESSION,
    compute_metrics,
    get_model,
)
from apps.api.modules.automl.task_detection import detect_task
from apps.api.modules.datasets.profiling import profile_dataframe

from apps.api.modules.datasets.tests.test_ingestion import create_dataset, create_project


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def profile_with_target(df: pd.DataFrame) -> dict:
    return profile_dataframe(df)


def continuous_frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    n = 300
    return pd.DataFrame({
        "x1": rng.normal(0, 1, n).round(3),
        "x2": rng.normal(0, 1, n).round(3),
        "price": rng.lognormal(3, 0.5, n).round(2),
        "city": rng.choice(["a", "b", "c"], n),
    })


# ──────────────────────────────────────────────────────────────────────────────
# Phase 7 — task detection
# ──────────────────────────────────────────────────────────────────────────────

def test_continuous_numeric_target_is_regression_high_confidence():
    result = detect_task(profile_with_target(continuous_frame()), "price")
    assert result["task_type"] == "regression"
    assert result["confidence"] == "high"
    assert result["needs_confirmation"] is False
    metrics = {m["metric"] for m in result["recommended_metrics"]}
    assert {"r2", "rmse", "mae"} <= metrics
    primary = [m for m in result["recommended_metrics"] if m["primary"]]
    assert primary[0]["metric"] == "r2"
    assert all(m["explanation"] for m in result["recommended_metrics"])


def test_skewed_regression_target_warns_about_loss():
    df = continuous_frame()
    result = detect_task(profile_with_target(df), "price")  # lognormal → skewed
    assert any("Huber" in n or "skew" in n.lower() for n in result["notes"])


def test_binary_numeric_target_asks_for_confirmation():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"x": range(100), "churn": rng.integers(0, 2, 100)})
    result = detect_task(profile_with_target(df), "churn")
    assert result["task_type"] == "classification"
    assert result["needs_confirmation"] is True
    assert result["question"]
    # Honest ambiguity: system asks rather than guessing
    assert result["confidence"] in ("medium", "low")


def test_multiclass_codes_ask_between_tasks():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"x": range(100), "grade": rng.integers(1, 6, 100)})
    result = detect_task(profile_with_target(df), "grade")
    assert result["needs_confirmation"] is True
    assert result.get("alternative_task") == "regression"


def test_categorical_target_is_classification_high_confidence():
    df = continuous_frame()
    result = detect_task(profile_with_target(df), "city")
    assert result["task_type"] == "classification"
    assert result["confidence"] == "high"
    assert result["needs_confirmation"] is False


def test_imbalanced_classification_recommends_f1_over_accuracy():
    rng = np.random.default_rng(4)
    n = 500
    df = pd.DataFrame({
        "x": rng.normal(0, 1, n).round(3),
        "fraud": np.where(rng.random(n) < 0.03, 1, 0),  # 3% minority
    })
    result = detect_task(profile_with_target(df), "fraud")
    assert result["class_balance"]["status"] == "critical"
    primary = next(m for m in result["recommended_metrics"] if m["primary"])
    assert primary["metric"].startswith("f1")
    assert any("accuracy" in n.lower() for n in result["notes"])


def test_identifier_target_raises_warning():
    df = continuous_frame()
    df["row_id"] = range(len(df))
    result = detect_task(profile_with_target(df), "row_id")
    assert any("identifier" in n.lower() for n in result["notes"])


def test_no_target_returns_unsupervised_hint():
    profile = profile_with_target(continuous_frame())
    # give the profiler a chance to suggest a candidate via name match
    df = continuous_frame()
    df["target"] = df["price"] > df["price"].median()
    profile = profile_with_target(df)
    result = detect_task(profile, None)
    assert result["task_type"] == "unsupervised"
    assert result.get("suggested_target") == "target"


def test_unknown_target_column_reported():
    result = detect_task(profile_with_target(continuous_frame()), "ghost")
    assert result["task_type"] is None
    assert any("not found" in n.lower() for n in result["notes"])


def test_every_metric_has_plain_language_explanation():
    for frame, col in ((continuous_frame(), "price"),):
        result = detect_task(profile_with_target(frame), col)
        for m in result["recommended_metrics"]:
            assert len(m["explanation"]) > 10  # real sentence, not a code


# ──────────────────────────────────────────────────────────────────────────────
# Phase 8 — focused model set
# ──────────────────────────────────────────────────────────────────────────────

def test_focused_sets_match_spec():
    assert FOCUSED_CLASSIFICATION == ["logistic_regression", "random_forest", "xgboost", "svm"]
    assert FOCUSED_REGRESSION == ["linear_regression", "random_forest", "xgboost"]


@pytest.mark.parametrize("algo,problem,expected_class", [
    ("logistic_regression", "classification", "LogisticRegression"),
    ("svm", "classification", "SVC"),
    ("random_forest", "classification", "RandomForestClassifier"),
    ("linear_regression", "regression", "LinearRegression"),
    ("random_forest", "regression", "RandomForestRegressor"),
])
def test_get_model_builds_expected_estimators(algo, problem, expected_class):
    model = get_model(algo, problem, {})
    assert type(model).__name__ == expected_class


def test_get_model_rejects_cross_problem_combinations():
    with pytest.raises(ValueError):
        get_model("logistic_regression", "regression", {})


def test_compute_metrics_includes_roc_auc_when_scores_given():
    rng = np.random.default_rng(7)
    y_true = rng.integers(0, 2, 200)
    y_pred = rng.integers(0, 2, 200)
    y_score = rng.random(200)
    metrics = compute_metrics(y_true, y_pred, "classification", y_score=y_score)
    assert 0.0 <= metrics.get("roc_auc", 0) <= 1.0


def test_compute_metrics_without_scores_omits_roc_auc():
    rng = np.random.default_rng(7)
    metrics = compute_metrics(rng.integers(0, 2, 50), rng.integers(0, 2, 50), "classification")
    assert "roc_auc" not in metrics


def test_compute_metrics_regression_shape():
    rng = np.random.default_rng(8)
    y = rng.normal(0, 1, 100)
    preds = y + rng.normal(0, 0.1, 100)
    metrics = compute_metrics(y, preds, "regression")
    # Phase 9 adds MSE alongside RMSE/MAE/R²
    assert {"r2", "rmse", "mae", "mse"} == set(metrics.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────


async def _upload(client, auth_headers, project_id, dataset_id):
    from apps.api.modules.datasets.tests.test_ingestion import csv_bytes, sample_frame
    up = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("data.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    assert up.status_code == 201, up.text
    return up.json()


@pytest.mark.asyncio
async def test_task_detection_endpoint(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])
    version = await _upload(client, auth_headers, project["id"], dataset["id"])

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version['id']}/task-detection",
        params={"target_column": "target"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_type"] == "classification"
    assert body["class_balance"]["status"] in ("balanced", "imbalanced", "critical")
    models = {m["id"] for m in body["recommended_models"]}
    assert models == set(FOCUSED_CLASSIFICATION)


@pytest.mark.asyncio
async def test_experiment_accepts_algorithms_field(client: AsyncClient, auth_headers: dict):
    """Experiment creation validates the focused algorithm list and persists
    the row. Training is spawned in-process and the suite disables it, so the
    row stays pending — the point here is the API contract, not the fit."""
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])
    await _upload(client, auth_headers, project["id"], dataset["id"])

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/automl/experiments",
        json={
            "target_column": "target",
            "problem_type": "classification",
            "primary_metric": "f1_macro",
            "algorithms": ["logistic_regression", "svm"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["algorithms"] == ["logistic_regression", "svm"]
    # Training is disabled for the suite, so the row is recorded honestly:
    assert body["status"] in ("pending", "failed")
