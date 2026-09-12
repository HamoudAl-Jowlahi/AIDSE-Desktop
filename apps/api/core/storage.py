"""
AIDSE Platform — Centralized Storage & Directory Management
Ensures all data (datasets, models, MLflow tracking, logs) are stored
in user-writable directories (e.g. %LOCALAPPDATA%\\AIDSE-Desktop)
rather than relying on CWD or Program Files install directories.
"""
from __future__ import annotations

import os
from pathlib import Path


def get_aidse_data_dir() -> Path:
    """
    Returns the root directory for AIDSE user-writable data.
    On Windows: %LOCALAPPDATA%\\AIDSE-Desktop
    On POSIX: ~/.local/share/AIDSE-Desktop or ~/AIDSE-Desktop
    """
    custom_dir = os.getenv("AIDSE_DATA_DIR")
    if custom_dir:
        data_dir = Path(custom_dir).resolve()
    elif os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        data_dir = Path(local_app_data) / "AIDSE-Desktop"
    else:
        data_dir = Path.home() / ".local" / "share" / "AIDSE-Desktop"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_storage_root() -> Path:
    """Returns the persistent storage directory for datasets and artifacts."""
    storage_dir = get_aidse_data_dir() / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def get_dataset_storage_dir(project_id: str) -> Path:
    """Returns the storage path for a project's dataset files."""
    proj_storage = get_storage_root() / "datasets" / str(project_id)
    proj_storage.mkdir(parents=True, exist_ok=True)
    return proj_storage


def get_mlflow_tracking_uri() -> str:
    """Returns the SQLite tracking URI for MLflow inside the user data directory."""
    db_file = (get_aidse_data_dir() / "mlruns.db").resolve()
    db_file_str = str(db_file).replace("\\", "/")
    return f"sqlite:///{db_file_str}"


def get_mlflow_artifact_uri() -> str:
    """
    Where MLflow writes run artifacts (models, plots, requirements files).

    The tracking URI only decides where run *metadata* goes. Artifacts default
    to ./mlruns relative to the working directory, which meant training from a
    checkout dumped megabytes of model files into the source tree — and an app
    started from a different directory could not find them again.
    """
    artifacts = get_aidse_data_dir() / "mlartifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts.resolve().as_uri()


def get_startup_error_log_path() -> Path:
    """Returns the canonical path for logging early startup exceptions."""
    return get_aidse_data_dir() / "startup_error.log"

