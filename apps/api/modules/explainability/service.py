"""
AIDSE Platform — Explainable AI Service (Phase 10)

Model-aware explanation strategies:

    Tree ensembles   → SHAP TreeExplainer (exact, fast)
    Linear models    → coefficient × value contributions (exact, signed)
    Other (SVM…)     → SHAP KernelExplainer on a small background sample

Every response carries plain-English insight plus, where available,
the DIRECTION of each feature's effect (raises vs lowers the prediction).
The original SHAP paths are preserved unchanged for tree models.
"""
import logging
import io
import base64
import uuid
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import shap
try:
    import mlflow
except Exception:
    mlflow = None

from sqlalchemy import select
from apps.api.db.session import AsyncSessionLocal
from apps.api.modules.automl.models import Experiment, ModelTrial
from apps.api.modules.datasets.models import DatasetVersion
from apps.api.modules.automl.service import preprocess_data, MLFLOW_DB_PATH

logger = logging.getLogger(__name__)

if mlflow is not None and hasattr(mlflow, "set_tracking_uri") and MLFLOW_DB_PATH:
    try:
        mlflow.set_tracking_uri(MLFLOW_DB_PATH)
    except Exception as exc:
        logger.warning("Could not set MLflow tracking URI: %s", exc)

TREE_ALGOS = {"random_forest", "xgboost", "lightgbm", "catboost"}
LINEAR_ALGOS = {"logistic_regression", "linear_regression"}


async def _get_trial_and_data(trial_id: uuid.UUID):
    async with AsyncSessionLocal() as db:
        stmt = select(ModelTrial).where(ModelTrial.id == trial_id)
        trial = (await db.execute(stmt)).scalar_one_or_none()
        if not trial:
            raise ValueError("Trial not found")
            
        stmt = select(Experiment).where(Experiment.id == trial.experiment_id)
        experiment = (await db.execute(stmt)).scalar_one_or_none()
        
        stmt = select(DatasetVersion).where(DatasetVersion.dataset_id == experiment.dataset_id).order_by(DatasetVersion.created_at.desc()).limit(1)
        latest_version = (await db.execute(stmt)).scalar_one_or_none()
        
        return trial, experiment, latest_version


def _img_to_base64() -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close()
    return encoded


def _load_model_and_data(trial, experiment, latest_version):
    if mlflow is None:
        raise RuntimeError("MLflow runtime is not installed or available on this system.")
    model_uri = f"runs:/{trial.mlflow_run_id}/model"
    model = mlflow.sklearn.load_model(model_uri)
    df = pd.read_csv(latest_version.s3_key)
    X, y, _ = preprocess_data(df, experiment.target_column, experiment.problem_type)
    return model, X


def _direction_word(contribution: float) -> str:
    return "pushes the prediction up" if contribution > 0 else (
        "pushes the prediction down" if contribution < 0 else "has no effect here"
    )


# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL explanation
# ──────────────────────────────────────────────────────────────────────────────

async def generate_global_shap(trial_id: uuid.UUID) -> dict:
    trial, experiment, latest_version = await _get_trial_and_data(trial_id)
    
    if not trial.mlflow_run_id:
        raise ValueError("No MLflow run ID found for this trial. Model was not logged.")
        
    model, X = _load_model_and_data(trial, experiment, latest_version)

    if len(X) > 1000:
        X_sample = X.sample(1000, random_state=42)
    else:
        X_sample = X

    method = _method_for(trial.algorithm_name, model)

    if method == "shap_tree":
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)

        if isinstance(shap_values, list):
            shap_values_to_plot = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        else:
            shap_values_to_plot = shap_values

        plt.figure()
        shap.summary_plot(shap_values_to_plot, X_sample, show=False)
        img_base64 = _img_to_base64()

        vals = np.abs(shap_values_to_plot).mean(0)
        importances_dict = dict(sorted(
            zip(X_sample.columns, [float(v) for v in vals]),
            key=lambda kv: kv[1], reverse=True,
        )[:5])

        insight = (
            f"The most influential feature driving this {trial.algorithm_name.replace('_', ' ')} "
            f"model is '{importances_dict and list(importances_dict)[0]}'. Features further right "
            "in the plot push individual predictions higher; features on the left pull them lower."
        )
        directions = None

    elif method == "coefficients":
        coefs = np.ravel(model.coef_)
        if coefs.ndim > 1:  # multiclass: average absolute effect across classes
            coef_series = pd.Series(np.abs(coefs).mean(axis=0), index=X.columns)
        else:
            coef_series = pd.Series(np.abs(coefs), index=X.columns)
        coef_series = coef_series.sort_values(ascending=False).head(12)

        plt.figure(figsize=(8, 4))
        colors = ["#2ecc71" if c >= 0 else "#e74c3c"
                  for c in (pd.Series(np.ravel(model.coef_), index=X.columns).loc[coef_series.index])]
        plt.barh(range(len(coef_series))[::-1], coef_series.values, color=colors)
        plt.yticks(range(len(coef_series))[::-1], coef_series.index)
        plt.xlabel("|coefficient| — influence on prediction")
        plt.title(f"How '{trial.algorithm_name.replace('_', ' ')}' weighs each feature")
        img_base64 = _img_to_base64()

        importances_dict = {k: float(v) for k, v in coef_series.iloc[:5].items()}
        raw_signs = pd.Series(np.ravel(model.coef_), index=X.columns).iloc[:, 0] if coefs.ndim > 1 \
            else pd.Series(np.ravel(model.coef_), index=X.columns)
        directions = {
            col: _direction_word(float(raw_signs.get(col, 0.0)))
            for col in list(coef_series.index)[:5]
        }
        insight = (
            "This linear model multiplies each feature by a learned weight. Green bars "
            "push predictions UP as the feature grows; red bars push them DOWN."
        )

    else:  # permutation importance — model-agnostic fallback
        from sklearn.inspection import permutation_importance
        from sklearn.model_selection import train_test_split as _tts

        _, X_hold = _tts(X, test_size=min(0.3, len(X)), random_state=42)
        if len(X_hold) > 500:
            X_hold = X_hold.sample(500, random_state=42)
        perm = permutation_importance(model, X_hold, model.predict(X_hold),
                                      n_repeats=5, random_state=42)
        series = pd.Series(perm.importances_mean, index=X.columns).sort_values(ascending=False).head(12)

        plt.figure(figsize=(8, 4))
        plt.barh(range(len(series))[::-1], series.values, color="#3498db")
        plt.yticks(range(len(series))[::-1], series.index)
        plt.xlabel("How much accuracy drops when this feature is shuffled")
        img_base64 = _img_to_base64()

        importances_dict = {k: float(v) for k, v in series.iloc[:5].items()}
        directions = None
        insight = (
            "Importance here measures how much the model's score drops when a feature's "
            "values are randomly shuffled — bigger drop means the model relies on it more."
        )

    return {
        "summary_plot_base64": img_base64,
        "feature_importances": importances_dict,
        "insight": insight,
        "explanation_method": method,
        "directions": directions,
    }


# ──────────────────────────────────────────────────────────────────────────────
# LOCAL explanation (single prediction)
# ──────────────────────────────────────────────────────────────────────────────

async def generate_local_shap(trial_id: uuid.UUID, row_index: int = 0) -> dict:
    trial, experiment, latest_version = await _get_trial_and_data(trial_id)
    
    model, X = _load_model_and_data(trial, experiment, latest_version)
    
    if row_index >= len(X) or row_index < 0:
        raise ValueError(f"Row index out of bounds. Must be between 0 and {len(X)-1}")
        
    row_data = X.iloc[[row_index]]
    prediction = model.predict(row_data)[0]
    method = _method_for(trial.algorithm_name, model)

    if method == "shap_tree":
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(row_data)
        expected_value = explainer.expected_value
        
        if isinstance(shap_values, list):
            shap_vals = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
            base_val = expected_value[1] if isinstance(expected_value, (list, np.ndarray)) and len(expected_value) > 1 else (expected_value[0] if isinstance(expected_value, (list, np.ndarray)) else expected_value)
        else:
            shap_vals = shap_values[0]
            base_val = expected_value[0] if isinstance(expected_value, (list, np.ndarray)) else expected_value
            
        plt.figure()
        try:
            shap.waterfall_plot(shap.Explanation(values=shap_vals, base_values=base_val, data=row_data.iloc[0].values, feature_names=X.columns.tolist()), show=False)
        except Exception:
            shap.bar_plot(shap_vals, feature_names=X.columns.tolist(), show=False)
            
        img_base64 = _img_to_base64()

    elif method == "coefficients":
        coefs = np.ravel(model.coef_)
        mean_vals = X.mean()
        contrib = (row_data.iloc[0] - mean_vals) * (coefs if coefs.ndim == 1 else coefs.mean(axis=0))
        top = contrib.abs().sort_values(ascending=False).head(8)
        contrib_top = contrib.loc[top.index]

        base_val = float(getattr(model, "intercept_", np.mean(model.predict(X)).item()))
        if hasattr(base_val, "__len__"):
            base_val = float(np.ravel(base_val)[0])

        plt.figure(figsize=(8, 4))
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in contrib_top.values]
        plt.barh(range(len(contrib_top))[::-1], contrib_top.values, color=colors)
        plt.yticks(range(len(contrib_top))[::-1], contrib_top.index)
        plt.xlabel(f"contribution toward prediction ({'class' if prediction is not None else ''})")
        plt.title(f"Why this row predicts {_truncate(prediction)}")
        img_base64 = _img_to_base64()

        shap_vals = contrib.values
        insight_note = None

    else:  # kernel SHAP on small background
        background = shap.sample(X, min(50, len(X)), random_state=42)
        explainer = shap.KernelExplainer(
            lambda data: model.predict(pd.DataFrame(data, columns=X.columns)), background
        )
        sv = explainer.shap_values(row_data, silent=True)
        arr = np.asarray(sv)
        shap_vals = np.ravel(arr[0]) if arr.ndim > 1 else np.ravel(arr)
        base_val = float(np.ravel(explainer.expected_value)[0]) if np.ndim(explainer.expected_value) else float(explainer.expected_value)

        order = np.argsort(-np.abs(shap_vals))[:8]
        plt.figure(figsize=(8, 4))
        vals_sorted = shap_vals[order]
        names = [X.columns[i] for i in order]
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in vals_sorted]
        plt.barh(range(len(names))[::-1], vals_sorted, color=colors)
        plt.yticks(range(len(names))[::-1], names)
        plt.xlabel("SHAP contribution to this prediction")
        img_base64 = _img_to_base64()

    row_dict = {col: str(val) for col, val in row_data.iloc[0].items()}
    shap_dict = {col: round(float(val), 6) for col, val in zip(X.columns, np.atleast_1d(shap_vals)[:len(X.columns)])}

    # Plain-English local narrative with directions
    top_contribs = sorted(shap_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
    parts = [
        f"'{col}' ({_direction_word(val)})" for col, val in top_contribs if val != 0
    ]
    narrative = (
        f"For this row the model predicted {_truncate(prediction)}. "
        + (f"The biggest drivers: " + ", ".join(parts) + "." if parts else "No single dominant driver.")
    )

    return {
        "force_plot_base64": img_base64,
        "row_values": row_dict,
        "shap_values": shap_dict,
        "base_value": float(base_val),
        "prediction": float(prediction),
        "explanation_method": method,
        "narrative": narrative,
    }


def _method_for(algorithm_name: str, model) -> str:
    if algorithm_name in TREE_ALGOS:
        return "shap_tree"
    # Linear models only expose coef_ after fitting — trust the algorithm id
    # first, then fall back to introspection for anything else that qualifies.
    if algorithm_name in LINEAR_ALGOS or (model is not None and hasattr(model, "coef_")):
        return "coefficients"
    return "kernel_shap"


def _truncate(value, length: int = 40) -> str:
    text = str(value)
    return text if len(text) <= length else text[:length] + "…"
