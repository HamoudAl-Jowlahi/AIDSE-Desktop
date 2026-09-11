"""
AIDSE Platform — Data Preparation Workbench engine (Phase 5)

Applies user-approved transformation steps to a dataset version and writes
the result to a NEW file. The original upload is never mutated.

Every successfully applied step produces a history record so the UI can
render an auditable "Step 1 … Step N" trail.

Supported actions
─────────────────
Structure      : drop_column, drop_duplicates, drop_na
Missing values : fillna_mean, fillna_median, fillna_mode,
                 fillna_constant (params.value)
Encoding       : one_hot_encode, label_encode, frequency_encode
Scaling        : standard_scale, minmax_scale, robust_scale
Outliers       : cap_outliers (IQR), drop_outliers (IQR),
                 winsorize (params.lower_pct/upper_pct), log_transform
Type conversion: convert_type (params.to = numeric|string|boolean|datetime)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_PREVIEW_ROWS = 200_000


class TransformError(Exception):
    """User-facing transformation failure."""


def _require_column(df: pd.DataFrame, col: str | None, action: str) -> str:
    if not col or col not in df.columns:
        raise TransformError(f"Column '{col}' not found for action '{action}'.")
    return col


def _apply_step(df: pd.DataFrame, step_no: int, step: dict[str, Any]) -> dict[str, Any]:
    action = step.get("action")
    col = step.get("column")
    params: dict[str, Any] = step.get("params") or {}

    def numeric(colname: str) -> pd.Series:
        series = df[colname]
        converted = pd.to_numeric(series, errors="coerce")
        if not pd.api.types.is_numeric_dtype(converted):
            raise TransformError(f"Column '{colname}' is not numeric; cannot apply '{action}'.")
        return converted

    if action == "drop_duplicates":
        before = len(df)
        df.drop_duplicates(inplace=True)
        dropped = before - len(df)
        note = f"{dropped} duplicate rows removed" if dropped else "no duplicates found"

    elif action == "drop_column":
        _require_column(df, col, action)
        df.drop(columns=[col], inplace=True)
        note = f"column removed ({df.shape[1]} remain)"

    elif action == "drop_na":
        _require_column(df, col, action)
        before = len(df)
        df.dropna(subset=[col], inplace=True)
        note = f"{before - len(df)} rows dropped"

    elif action == "fillna_mean":
        c = _require_column(df, col, action)
        s = numeric(c)
        df[c] = df[c].fillna(float(s.mean()))
        note = "missing values filled with column mean"
    elif action == "fillna_median":
        c = _require_column(df, col, action)
        s = numeric(c)
        df[c] = df[c].fillna(float(s.median()))
        note = "missing values filled with column median"
    elif action == "fillna_mode":
        c = _require_column(df, col, action)
        mode_val = df[c].mode()
        if mode_val.empty:
            raise TransformError(f"Cannot compute a mode for '{c}' (all values missing).")
        df[c] = df[c].fillna(mode_val.iloc[0])
        note = "missing values filled with most frequent value"
    elif action == "fillna_constant":
        c = _require_column(df, col, action)
        value = params.get("value")
        if value is None:
            raise TransformError("'fillna_constant' requires params.value.")
        df[c] = df[c].fillna(value)
        note = f"missing values filled with constant {value!r}"

    elif action == "one_hot_encode":
        c = _require_column(df, col, action)
        dummies = pd.get_dummies(df[c], prefix=str(c), dtype=int)
        if dummies.shape[1] > 100:
            raise TransformError(
                f"'{c}' has too many distinct values ({dummies.shape[1]}) for one-hot "
                "encoding — use frequency encoding instead."
            )
        df.drop(columns=[c], inplace=True)
        for dcol in dummies.columns:
            df[dcol] = dummies[dcol]
        note = f"expanded into {dummies.shape[1]} indicator columns"

    elif action == "label_encode":
        c = _require_column(df, col, action)
        codes, uniques = pd.factorize(df[c])
        df[c] = codes.astype("Int64")
        note = f"encoded {len(uniques)} categories as integers"

    elif action == "frequency_encode":
        c = _require_column(df, col, action)
        freq = df[c].value_counts(normalize=True)
        df[c] = df[c].map(freq).astype(float)
        note = "categories replaced by their relative frequency"

    elif action == "standard_scale":
        c = _require_column(df, col, action)
        s = numeric(c)
        std = float(s.std())
        mean = float(s.mean())
        if std == 0 or np.isnan(std):
            raise TransformError(f"Cannot scale '{c}' — zero variance.")
        df[c] = (df[c] - mean) / std
        note = "mean-centered, unit variance"

    elif action == "minmax_scale":
        c = _require_column(df, col, action)
        s = numeric(c)
        rng = float(s.max() - s.min())
        if rng == 0 or np.isnan(rng):
            raise TransformError(f"Cannot scale '{c}' — zero range.")
        df[c] = (df[c] - float(s.min())) / rng
        note = "scaled into [0, 1]"

    elif action == "robust_scale":
        c = _require_column(df, col, action)
        s = numeric(c)
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        if iqr == 0:
            raise TransformError(f"Cannot robust-scale '{c}' — zero IQR.")
        df[c] = (df[c] - float(s.median())) / iqr
        note = "median/IQR scaled (robust to outliers)"

    elif action == "cap_outliers":
        c = _require_column(df, col, action)
        s = numeric(c)
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        df[c] = df[c].clip(lower=lower, upper=upper)
        note = f"values clipped to [{round(lower, 4)}, {round(upper, 4)}]"

    elif action == "winsorize":
        c = _require_column(df, col, action)
        s = numeric(c)
        lo_pct = float(params.get("lower_pct", 0.01))
        hi_pct = float(params.get("upper_pct", 0.99))
        lo, hi = float(s.quantile(lo_pct)), float(s.quantile(hi_pct))
        df[c] = df[c].clip(lower=lo, upper=hi)
        note = f"capped at p{int(lo_pct * 100)}/p{int(hi_pct * 100)} = [{round(lo, 4)}, {round(hi, 4)}]"

    elif action == "drop_outliers":
        c = _require_column(df, col, action)
        s = numeric(c)
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        before = len(df)
        keep_mask = df[c].isna() | ((df[c] >= lower) & (df[c] <= upper))
        df.drop(index=df.index[~keep_mask], inplace=True)
        note = f"{before - len(df)} outlier rows removed"

    elif action == "log_transform":
        c = _require_column(df, col, action)
        s = numeric(c)
        if (s.dropna() <= 0).any():
            # shift into positive domain so zeros/negatives survive
            shift = float(-s.min()) + 1.0
            df[c] = np.log1p(df[c] + shift)
            note = f"log1p applied after +{round(shift, 4)} shift (non-positive values present)"
        else:
            df[c] = np.log1p(df[c])
            note = "log1p applied"

    elif action == "convert_type":
        c = _require_column(df, col, action)
        target = str(params.get("to", "")).lower()
        if target == "numeric":
            converted = pd.to_numeric(df[c], errors="coerce")
            failed = int((df[c].notna() & converted.isna()).sum())
            df[c] = converted
            note = f"converted to numeric ({failed} values became NaN)" if failed else "converted to numeric"
        elif target == "string":
            df[c] = df[c].astype(str)
            note = "converted to string"
        elif target == "boolean":
            mapping = {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False, "y": True, "n": False}
            df[c] = df[c].map(lambda v: mapping.get(str(v).strip().lower(), v)).astype("boolean")
            note = "converted to boolean"
        elif target == "datetime":
            converted = pd.to_datetime(df[c], errors="coerce")
            failed = int((df[c].notna() & converted.isna()).sum())
            df[c] = converted
            note = f"parsed as datetime ({failed} unparseable → NaT)" if failed else "parsed as datetime"
        else:
            raise TransformError("'convert_type' requires params.to ∈ numeric|string|boolean|datetime.")

    else:
        raise TransformError(f"Unknown action '{action}'.")

    return {
        "step_no": step_no,
        "action": action,
        "column": col,
        "params": params or None,
        "note": note,
    }


def apply_transformations(
    input_path: str,
    output_path: str,
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Apply steps sequentially and write result to output_path.
    Returns the history records for applied steps.
    Raises TransformError with a user-facing message on failure.
    """
    try:
        df = pd.read_csv(input_path)
    except Exception as exc:
        raise TransformError(f"Could not read source file: {exc}") from exc

    history: list[dict[str, Any]] = []
    for i, step in enumerate(steps, start=1):
        try:
            history.append(_apply_step(df, i, step))
        except TransformError:
            raise
        except Exception as exc:  # unexpected pandas error → still user-facing
            logger.exception("Transform step %s failed", i)
            raise TransformError(f"Step {i} ('{step.get('action')}') failed: {exc}") from exc

    try:
        df.to_csv(output_path, index=False)
    except Exception as exc:
        raise TransformError(f"Failed to save transformed file: {exc}") from exc
    return history


def preview_transformations(
    input_path: str,
    steps: list[dict[str, Any]],
    n_preview: int = 20,
) -> dict[str, Any]:
    """
    Dry-run steps on an in-memory copy (never persisted).
    Large frames are truncated to MAX_PREVIEW_ROWS and flagged.
    """
    try:
        df = pd.read_csv(input_path)
    except Exception as exc:
        raise TransformError(f"Could not read source file: {exc}") from exc

    truncated = False
    if len(df) > MAX_PREVIEW_ROWS:
        df = df.head(MAX_PREVIEW_ROWS).copy()
        truncated = True

    before_cols = list(map(str, df.columns))
    before_nulls = df.isna().sum().to_dict()
    before_dtypes = {c: str(t) for c, t in df.dtypes.items()}
    before_rows = len(df)
    sample_before = df.head(n_preview).replace({np.nan: None}).to_dict(orient="records")

    history: list[dict[str, Any]] = []
    error: str | None = None
    for i, step in enumerate(steps, start=1):
        try:
            history.append(_apply_step(df, i, step))
        except TransformError as exc:
            error = str(exc)
            break

    sample_after: list[dict[str, Any]] = []
    changed_columns: list[dict[str, Any]] = []
    if error is None:
        sample_after = df.head(n_preview).replace({np.nan: None}).to_dict(orient="records")
        after_dtypes = {str(c): str(t) for c, t in df.dtypes.items()}
        after_nulls = df.isna().sum().to_dict()
        seen = set(before_cols) | set(after_dtypes)
        for c in seen:
            entry: dict[str, Any] = {"column": c}
            if c not in before_dtypes:
                entry["change"] = "added"; changed_columns.append(entry); continue
            if c not in after_dtypes:
                entry["change"] = "removed"; changed_columns.append(entry); continue
            if before_dtypes[c] != after_dtypes[c]:
                entry["change"] = "dtype"; entry["before"] = before_dtypes[c]; entry["after"] = after_dtypes[c]
                changed_columns.append(entry)
            elif before_nulls.get(c, 0) != after_nulls.get(c, 0):
                entry["change"] = "nulls"
                entry["before"] = int(before_nulls.get(c, 0)); entry["after"] = int(after_nulls.get(c, 0))
                changed_columns.append(entry)

    return {
        "ok": error is None,
        "error": error,
        "truncated_for_preview": truncated,
        "rows_before": before_rows,
        "rows_after": len(df),
        "columns_before": len(before_cols),
        "columns_after": int(df.shape[1]),
        "applied_steps": history,
        "sample_before": sample_before[:n_preview],
        "sample_after": sample_after[:n_preview],
        "changed_columns": changed_columns,
    }
