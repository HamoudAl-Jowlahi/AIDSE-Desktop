"""
AIDSE Platform — Dataset Ingestion (Phase 2)

File validation and loading for CSV / XLSX / XLS uploads.

Design decisions:
- Uploads are validated by extension + size + readability before touching the DB.
- Every stored file is normalized to CSV on disk, so downstream consumers
  (transformations, downloads, ML training) handle exactly one canonical format.
- Never executes anything from uploaded files; only pandas readers are used.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB hard limit per upload

# Files above this size are profiled in a background task instead of inline.
INLINE_PROFILE_MAX_BYTES = 15 * 1024 * 1024


class FileValidationError(Exception):
    """Raised when an uploaded file fails validation. Message is user-facing."""


def detect_format(filename: str | None) -> str:
    """
    Return the lowercase extension (with dot) of an uploaded filename.
    Raises FileValidationError for unsupported or missing extensions.
    """
    if not filename:
        raise FileValidationError("Uploaded file has no filename.")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        supported = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise FileValidationError(
            f"Unsupported file type '{ext}'. Supported formats: {supported}."
        )
    return ext


def validate_upload_size(raw: bytes) -> None:
    """Reject empty and oversized uploads before any parsing work."""
    if len(raw) == 0:
        raise FileValidationError("Uploaded file is empty.")
    if len(raw) > MAX_FILE_SIZE_BYTES:
        limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise FileValidationError(f"File exceeds the {limit_mb} MB upload limit.")


def load_dataframe(path: str, fmt: str) -> pd.DataFrame:
    """
    Load a dataset file from disk into a DataFrame.

    fmt must be one of '.csv', '.xlsx', '.xls'.
    Raises FileValidationError on unreadable/empty-tabular files.
    """
    try:
        if fmt == ".csv":
            df = pd.read_csv(path)
        elif fmt in (".xlsx", ".xls"):
            engine = "openpyxl" if fmt == ".xlsx" else "xlrd"
            df = pd.read_excel(path, engine=engine)
        else:  # pragma: no cover - guarded by detect_format
            raise FileValidationError(f"Unsupported format '{fmt}'.")
    except FileValidationError:
        raise
    except Exception as exc:
        logger.warning("Failed to parse dataset file %s (%s): %s", path, fmt, exc)
        raise FileValidationError(
            "Could not read the file as a tabular dataset. It may be corrupt "
            "or not a valid CSV/Excel file."
        ) from exc

    df.columns = [str(c).strip() for c in df.columns]
    if df.shape[0] == 0:
        raise FileValidationError("The file contains no data rows.")
    if df.shape[1] == 0:
        raise FileValidationError("The file contains no columns.")
    return df


def save_dataframe_as_csv(df: pd.DataFrame, output_path: str) -> None:
    """Persist any loaded DataFrame to the canonical on-disk CSV format."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)


def sniff_target_candidate(df: pd.DataFrame) -> dict[str, Any]:
    """
    Heuristic target-column suggestion used when the user has not chosen one.

    Priority:
    1. Column named target/label/y/class/outcome (name match).
    2. Low-cardinality non-identifier column (classification-like), preferring
       columns near the end of the frame.
    3. Non-identifier numeric column (regression-like).

    Returns a JSON-serializable dict or None when no candidate exists.
    """
    name_matches = ("target", "label", "y", "class", "outcome")
    cols = list(df.columns)

    # 1. Name match wins outright
    for col in cols:
        if str(col).strip().lower() in name_matches:
            return _candidate_payload(df, col, confidence="name_match",
                                      reason="Column name suggests it is the target.")

    def is_identifier(col: str) -> bool:
        lowered = str(col).strip().lower()
        if lowered.endswith("_id") or lowered in ("id", "index", "uuid", "guid"):
            return True
        series = df[col]
        if pd.api.types.is_integer_dtype(series):
            unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
            if unique_ratio > 0.98:
                return True
        return False

    candidates = [c for c in cols if not is_identifier(str(c))]

    # 2. Classification-like: low-cardinality column (2..20 uniques)
    low_card = [
        c for c in reversed(candidates)
        if 2 <= df[c].nunique(dropna=True) <= min(20, max(2, len(df) // 10))
        and not pd.api.types.is_float_dtype(df[c])
    ]
    if low_card:
        col = low_card[0]
        return _candidate_payload(
            df, col, confidence="heuristic",
            reason="Low number of distinct values suggests a classification label.",
        )

    # 3. Regression-like: first remaining numeric column
    numeric_candidates = [c for c in candidates if pd.api.types.is_numeric_dtype(df[c])]
    if numeric_candidates:
        col = numeric_candidates[0]
        return _candidate_payload(
            df, col, confidence="weak",
            reason="Numeric column without obvious identifier traits; verify with the user.",
        )

    return None


def _candidate_payload(df: pd.DataFrame, col: Any, confidence: str, reason: str) -> dict[str, Any]:
    column = str(col)
    task_type = (
        "regression"
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].nunique(dropna=True) > 20
        else "classification"
    )
    return {
        "column": column,
        "task_type": task_type,
        "confidence": confidence,
        "reason": reason,
    }
