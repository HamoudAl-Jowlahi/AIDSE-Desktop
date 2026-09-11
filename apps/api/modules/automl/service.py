import logging
import asyncio
import os
import uuid
import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
import numpy as np
import optuna
os.environ["MLFLOW_LOG_UV_FILES"] = "false"
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
try:
    import mlflow
except Exception:
    mlflow = None
from sqlalchemy import select

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, KFold
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    f1_score, accuracy_score, precision_score, recall_score,
    mean_squared_error, r2_score, mean_absolute_error, roc_auc_score,
    confusion_matrix, classification_report,
)

from xgboost import XGBClassifier, XGBRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.svm import SVC, SVR

from apps.api.db.session import AsyncSessionLocal
from apps.api.modules.automl.models import Experiment, ModelTrial
from apps.api.modules.datasets.models import DatasetVersion

from apps.api.core.storage import get_mlflow_tracking_uri

logger = logging.getLogger(__name__)

MLFLOW_DB_PATH = get_mlflow_tracking_uri()
if mlflow is not None and hasattr(mlflow, "set_tracking_uri") and MLFLOW_DB_PATH:
    try:
        mlflow.set_tracking_uri(MLFLOW_DB_PATH)
    except Exception as exc:
        logger.warning("Could not set MLflow tracking URI: %s", exc)

# Phase 8 — focused default set. Advanced families (lightgbm, catboost)
# remain available but are opt-in via experiment.algorithms (V2 scope).
FOCUSED_CLASSIFICATION = ["logistic_regression", "random_forest", "xgboost", "svm"]
FOCUSED_REGRESSION = ["linear_regression", "random_forest", "xgboost"]

def preprocess_data(df: pd.DataFrame, target_column: str, problem_type: str):
    # Separate X and y and drop rows where target is missing
    valid_mask = df[target_column].notna()
    df_clean = df[valid_mask].copy()
    
    y = df_clean[target_column].copy()
    X = df_clean.drop(columns=[target_column])
    
    # Very basic preprocessing (in production, should use the pipeline stored in Dataset Intelligence)
    # Fill missing values
    for col in X.columns:
        if pd.api.types.is_numeric_dtype(X[col]):
            X[col] = X[col].fillna(X[col].median())
        else:
            X[col] = X[col].fillna(X[col].mode()[0] if not X[col].mode().empty else "Unknown")
            
    # Label encode categorical features
    encoders = {}
    for col in X.columns:
        if not pd.api.types.is_numeric_dtype(X[col]):
            le = LabelEncoder()
            # Convert to string to prevent mixed type errors
            X[col] = le.fit_transform(X[col].astype(str))
            encoders[col] = le

    target_classes = None
    if problem_type == "classification" and not pd.api.types.is_numeric_dtype(y):
        le_y = LabelEncoder()
        y = le_y.fit_transform(y.astype(str))
        target_classes = [str(c) for c in le_y.classes_]
    elif problem_type == "classification":
        target_classes = sorted({str(v) for v in y.unique()})

    return X, y, target_classes

def _get_configured_performance() -> tuple[int, str]:
    try:
        from apps.api.modules.system.router import _read_desktop_settings
        settings = _read_desktop_settings()
        threads = int(settings.get("max_training_threads", 4))
        mode = str(settings.get("performance_mode", "balanced"))
        return threads, mode
    except Exception:
        return 4, "balanced"

def _get_configured_threads() -> int:
    threads, _ = _get_configured_performance()
    return threads

def _apply_windows_priority(mode: str) -> None:
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            handle = k32.GetCurrentProcess()
            # 0x00008000 = ABOVE_NORMAL_PRIORITY_CLASS (Turbo)
            # 0x00000020 = NORMAL_PRIORITY_CLASS (Balanced)
            priority = 0x00008000 if mode == "max" else 0x00000020
            k32.SetPriorityClass(handle, priority)
        except Exception:
            pass


def get_model(algorithm_name: str, problem_type: str, params: Dict[str, Any], threads: Optional[int] = None):
    if threads is None:
        threads = _get_configured_threads()

    if problem_type == "classification":
        if algorithm_name == "random_forest": return RandomForestClassifier(**params, n_jobs=threads, random_state=42)
        elif algorithm_name == "xgboost": return XGBClassifier(**params, n_jobs=threads, random_state=42)
        elif algorithm_name == "lightgbm": return LGBMClassifier(**params, n_jobs=threads, random_state=42, verbose=-1)
        elif algorithm_name == "catboost": return CatBoostClassifier(**params, thread_count=threads, random_state=42, verbose=0)
        elif algorithm_name == "logistic_regression": return LogisticRegression(max_iter=1000, n_jobs=threads, **params)
        elif algorithm_name == "svm": return SVC(kernel="rbf", cache_size=300, probability=True, random_state=42, **params)
    else:
        if algorithm_name == "random_forest": return RandomForestRegressor(**params, n_jobs=threads, random_state=42)
        elif algorithm_name == "xgboost": return XGBRegressor(**params, n_jobs=threads, random_state=42)
        elif algorithm_name == "lightgbm": return LGBMRegressor(**params, n_jobs=threads, random_state=42, verbose=-1)
        elif algorithm_name == "catboost": return CatBoostRegressor(**params, thread_count=threads, random_state=42, verbose=0)
        elif algorithm_name == "linear_regression": return LinearRegression(n_jobs=threads, **params)
    raise ValueError(f"Unknown algorithm {algorithm_name} for {problem_type}")

def compute_metrics(y_true, y_pred, problem_type: str, y_score=None) -> Dict[str, float]:
    if problem_type == "classification":
        metrics = {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
            "precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        }
        # Phase 8/9: rank-based AUC when class probabilities are available.
        if y_score is not None:
            try:
                if y_score.ndim == 1:
                    metrics["roc_auc"] = float(roc_auc_score(y_true, y_score))
                elif y_score.shape[1] == 2:
                    metrics["roc_auc"] = float(roc_auc_score(y_true, y_score[:, 1]))
                else:
                    metrics["roc_auc"] = float(
                        roc_auc_score(y_true, y_score, multi_class="ovr", average="macro")
                    )
            except Exception:
                pass  # single-class folds etc. — AUC simply omitted
        return metrics
    return {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mse": float(mean_squared_error(y_true, y_pred)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
    }

async def _run_automl_async(experiment_id: str):
    async with AsyncSessionLocal() as db:
        # Fetch experiment
        stmt = select(Experiment).where(Experiment.id == uuid.UUID(experiment_id))
        experiment = (await db.execute(stmt)).scalar_one_or_none()
        
        if not experiment:
            logger.error(f"Experiment {experiment_id} not found.")
            return

        # Mark as running
        experiment.status = "running"
        await db.commit()

        # Apply Windows Process Priority for Performance Mode (Balanced vs Turbo)
        threads, mode = _get_configured_performance()
        _apply_windows_priority(mode)

        try:
            # Fetch Dataset version to get S3 key
            stmt = select(DatasetVersion).where(DatasetVersion.dataset_id == experiment.dataset_id).order_by(DatasetVersion.created_at.desc()).limit(1)
            latest_version = (await db.execute(stmt)).scalar_one_or_none()
            
            if not latest_version:
                raise Exception("No dataset version found to train on.")
                
            file_path = latest_version.s3_key
            df = pd.read_csv(file_path)
            
            X, y, target_classes = preprocess_data(df, experiment.target_column, experiment.problem_type)
            X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, 
                stratify=y if experiment.problem_type == "classification" else None)
                
            if mlflow is not None and hasattr(mlflow, "set_experiment"):
                try:
                    mlflow.set_experiment(f"AIDSE_Experiment_{experiment_id}")
                except Exception as me:
                    logger.warning("MLflow set_experiment failed: %s", me)

            # Phase 8: honor user-selected algorithm set, else focused defaults
            algorithms: List[str] = getattr(experiment, "algorithms", None) or (
                FOCUSED_CLASSIFICATION if experiment.problem_type == "classification" else FOCUSED_REGRESSION
            )

            def objective(trial):
                algo = trial.suggest_categorical("algorithm", algorithms)

                params = {}
                if algo == "random_forest":
                    params["n_estimators"] = trial.suggest_int("n_estimators", 50, 300)
                    params["max_depth"] = trial.suggest_int("max_depth", 3, 20)
                elif algo == "xgboost":
                    params["n_estimators"] = trial.suggest_int("n_estimators", 50, 300)
                    params["learning_rate"] = trial.suggest_float("learning_rate", 1e-3, 0.5, log=True)
                    params["max_depth"] = trial.suggest_int("max_depth", 3, 15)
                elif algo == "lightgbm":
                    params["n_estimators"] = trial.suggest_int("n_estimators", 50, 300)
                    params["learning_rate"] = trial.suggest_float("learning_rate", 1e-3, 0.5, log=True)
                    params["num_leaves"] = trial.suggest_int("num_leaves", 20, 300)
                elif algo == "catboost":
                    params["iterations"] = trial.suggest_int("iterations", 50, 300)
                    params["learning_rate"] = trial.suggest_float("learning_rate", 1e-3, 0.5, log=True)
                    params["depth"] = trial.suggest_int("depth", 3, 12)
                elif algo == "logistic_regression":
                    params["C"] = trial.suggest_float("C", 1e-3, 100.0, log=True)
                elif algo == "svm":
                    params["C"] = trial.suggest_float("C", 1e-2, 100.0, log=True)
                    params["kernel"] = trial.suggest_categorical("kernel", ["rbf", "linear"])
                elif algo == "linear_regression":
                    params["fit_intercept"] = trial.suggest_categorical("fit_intercept", [True, False])

                run_id = None
                run = None
                if mlflow is not None and hasattr(mlflow, "start_run"):
                    try:
                        run = mlflow.start_run(nested=True)
                        run_id = run.info.run_id
                    except Exception as me:
                        logger.warning("MLflow start_run failed: %s", me)
                        run = None

                try:
                    model = get_model(algo, experiment.problem_type, params)
                    model.fit(X_train, y_train)
                    preds = model.predict(X_val)

                    metrics = compute_metrics(
                        y_val,
                        preds,
                        experiment.problem_type,
                        y_score=_class_scores(model, X_val) if experiment.problem_type == "classification" else None,
                    )

                    # Phase 9: rich evaluation artifacts stored alongside metrics
                    evaluation_extra: Dict[str, Any] = {}
                    if experiment.problem_type == "classification":
                        labels = target_classes or [str(v) for v in sorted(set(y_train) | set(y_val))]
                        cm = confusion_matrix(y_val, preds)
                        report = classification_report(
                            y_val, preds, output_dict=True, zero_division=0
                        )
                        per_class = {
                            label: {
                                "precision": round(report[str(i)]["precision"], 4),
                                "recall": round(report[str(i)]["recall"], 4),
                                "f1_score": round(report[str(i)]["f1-score"], 4),
                                "support": int(report[str(i)]["support"]),
                            }
                            for i, label in enumerate(labels[: len(report) - 2])
                            if str(i) in report
                        }
                        evaluation_extra["confusion_matrix"] = {
                            "labels": labels,
                            "matrix": cm.tolist(),
                        }
                        evaluation_extra["per_class"] = per_class
                    else:
                        pass  # mse already inside metrics

                    if run is not None and mlflow is not None and hasattr(mlflow, "log_params"):
                        try:
                            mlflow.log_params(params)
                            mlflow.log_param("algorithm", algo)
                            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
                            if hasattr(mlflow, "sklearn") and hasattr(mlflow.sklearn, "log_model"):
                                mlflow.sklearn.log_model(model, "model")
                        except Exception as log_err:
                            logger.warning("MLflow logging failed: %s", log_err)

                    primary_score = metrics.get(experiment.primary_metric, 0.0)

                    trial.set_user_attr("metrics", {**metrics, **evaluation_extra})
                    trial.set_user_attr("mlflow_run_id", run_id)
                    trial.set_user_attr("params", params)

                    return primary_score
                finally:
                    if run is not None and mlflow is not None and hasattr(mlflow, "end_run"):
                        try:
                            mlflow.end_run()
                        except Exception:
                            pass

            # We maximize f1, accuracy, r2; we minimize rmse, mae
            direction = "minimize" if experiment.primary_metric in ["rmse", "mae"] else "maximize"
            
            experiment.status = "running"
            await db.commit()

            study = optuna.create_study(direction=direction)
            created_trials: List[ModelTrial] = []

            for _ in range(10):
                trial = study.ask()
                val = await asyncio.to_thread(objective, trial)
                study.tell(trial, val)

                metrics = trial.user_attrs.get("metrics", {})
                clean_metrics = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))}
                primary_score = clean_metrics.get(experiment.primary_metric)
                algo = trial.params.get("algorithm")

                model_trial = ModelTrial(
                    experiment_id=experiment.id,
                    algorithm_name=algo,
                    hyperparameters=trial.user_attrs.get("params", {}),
                    metrics=clean_metrics,
                    primary_metric_score=primary_score,
                    mlflow_run_id=trial.user_attrs.get("mlflow_run_id"),
                    is_best=False,
                    status="completed"
                )
                db.add(model_trial)
                created_trials.append(model_trial)
                await db.commit()

            # Mark the winning trial
            best_trial_num = study.best_trial.number
            for idx, mt in enumerate(created_trials):
                if idx == best_trial_num:
                    mt.is_best = True

            experiment.status = "completed"
            experiment.error_message = None
            await db.commit()
            
        except Exception as e:
            logger.exception("AutoML experiment failed")
            experiment.status = "failed"
            experiment.error_message = str(e)
            await db.commit()
        finally:
            _apply_windows_priority("balanced")

def run_automl_experiment_task(experiment_id: str):
    """
    Celery task wrapper for AutoML
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_run_automl_async(experiment_id))
    else:
        asyncio.run(_run_automl_async(experiment_id))

def _class_scores(model, X_val):
    """
    Class-probability matrix for ROC-AUC; returns None for models without
    predict_proba so metrics stay valid instead of crashing the trial.
    """
    try:
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X_val)
            return proba if proba.ndim == 2 else None
    except Exception:
        pass
    return None
