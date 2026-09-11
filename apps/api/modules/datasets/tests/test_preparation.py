"""
AIDSE Platform — Outlier Intelligence + Preparation Workbench Tests (Phases 4-5)

Covers:
- Multi-method outlier detection (IQR, Z-score, Isolation Forest, LOF)
- Treatment recommendations (skew/share/task aware)
- Extended transformation actions (encoding, scaling, winsorize, types)
- Preview dry-run (no persistence)
- Transformation history + lineage + revert
- Before/after comparison endpoint
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from httpx import AsyncClient

from apps.api.modules.datasets.outliers import (
    detect_outliers,
    recommend_treatment,
    scan_numeric_columns,
)
from apps.api.modules.datasets.transform import (
    TransformError,
    apply_transformations,
    preview_transformations,
)

from apps.api.modules.datasets.tests.test_ingestion import (
    create_dataset,
    create_project,
    csv_bytes,
    sample_frame,
)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4 — detection methods
# ──────────────────────────────────────────────────────────────────────────────

def outlier_series() -> pd.Series:
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(50, 5, 300))
    s.iloc[0] = 500.0
    s.iloc[1] = -200.0
    return s


@pytest.mark.parametrize("method", ["iqr", "zscore", "isolation_forest", "lof"])
def test_all_methods_flag_injected_extremes(method):
    result = detect_outliers(outlier_series(), method=method)
    assert result["count"] >= 2
    assert set(result["params"].keys())


def test_iqr_returns_fences():
    r = detect_outliers(outlier_series(), method="iqr")
    assert r["params"]["lower_fence"] < r["params"]["upper_fence"]
    assert r["flagged_truncated"] is False


def test_zscore_threshold_recorded():
    r = detect_outliers(outlier_series(), method="zscore")
    assert r["params"]["threshold"] == 3.0


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        detect_outliers(outlier_series(), method="magic")


def test_constant_series_zero_outliers():
    r = detect_outliers(pd.Series([7.0] * 100), method="iqr")
    assert r["count"] == 0


def test_scan_numeric_columns_sorted_and_recommends():
    df = outlier_series().to_frame("values")
    df["id_col"] = range(len(df))
    items = scan_numeric_columns(df)
    assert items[0]["column"] == "values"
    assert items[0]["recommendation"]["technique"]
    # id-like column (monotonic) should flag ~half as IQR outliers but never recommend deletion first
    id_item = next(i for i in items if i["column"] == "id_col")
    assert id_item["recommendation"]["technique"]


def test_recommendation_keep_for_rare_extremes():
    col_stats = {"_num_rows": 10_000, "skew": 0.2}
    rec = recommend_treatment(col_stats, {"method": "iqr", "count": 30})
    assert rec["technique"].startswith("Keep")


def test_recommendation_transform_for_skewed():
    col_stats = {"_num_rows": 1_000, "skew": 3.5}
    rec = recommend_treatment(col_stats, {"method": "iqr", "count": 80})
    assert "transform" in rec["technique"].lower()


def test_recommendation_investigate_for_heavy_share():
    col_stats = {"_num_rows": 1_000, "skew": 0.4}
    rec = recommend_treatment(col_stats, {"method": "iqr", "count": 120})
    assert "Investigate" in rec["technique"]


# ──────────────────────────────────────────────────────────────────────────────
# Phase 5 — transformation engine
# ──────────────────────────────────────────────────────────────────────────────

def write_df(tmp_path, df):
    p = tmp_path / "in.csv"
    p.write_bytes(csv_bytes(df))
    return str(p)


def base_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "num": [1.0, 2.0, np.nan, 4.0, 1000.0],
            "cat": ["red", "blue", "red", None, "green"],
            "flag": ["yes", "no", "yes", "no", "yes"],
        }
    )


def test_fillna_median_creates_history(tmp_path):
    out = str(tmp_path / "out.csv")
    hist = apply_transformations(write_df(tmp_path, base_frame()), out,
                                 [{"action": "fillna_median", "column": "num"}])
    assert hist[0]["step_no"] == 1
    assert "median" in hist[0]["note"]
    df = pd.read_csv(out)
    assert df["num"].isna().sum() == 0
    assert df.loc[2, "num"] == pytest.approx(3.0)


def test_one_hot_encode_expands_columns(tmp_path):
    out = str(tmp_path / "out.csv")
    hist = apply_transformations(write_df(tmp_path, base_frame()), out,
                                 [{"action": "one_hot_encode", "column": "cat"}])
    df = pd.read_csv(out)
    assert "cat" not in df.columns
    assert any(c.startswith("cat_") for c in df.columns)
    assert "indicator columns" in hist[0]["note"]


def test_one_hot_encode_rejects_high_cardinality(tmp_path):
    n = 150
    df = pd.DataFrame(
        {
            "huge": [f"val_{i}" for i in range(n)],
            "y": range(n),
        }
    )
    with pytest.raises(TransformError):
        apply_transformations(write_df(tmp_path, df), str(tmp_path / "o.csv"),
                              [{"action": "one_hot_encode", "column": "huge"}])


def test_frequency_encode_handles_high_cardinality(tmp_path):
    n = 150
    df = pd.DataFrame({"huge": [f"val_{i % 10}" for i in range(n)]})
    out = str(tmp_path / "out.csv")
    apply_transformations(write_df(tmp_path, df), out,
                          [{"action": "frequency_encode", "column": "huge"}])
    assert pd.read_csv(out)["huge"].between(0, 1).all()


def test_scaling_actions(tmp_path):
    for action in ("standard_scale", "minmax_scale", "robust_scale"):
        out = str(tmp_path / f"{action}.csv")
        apply_transformations(write_df(tmp_path, base_frame()), out,
                              [{"action": "fillna_median", "column": "num"},
                               {"action": action, "column": "num"}])
        df = pd.read_csv(out)
        assert df["num"].notna().all()


def test_winsorize_caps_extreme(tmp_path):
    out = str(tmp_path / "out.csv")
    apply_transformations(write_df(tmp_path, base_frame()), out,
                          [{"action": "winsorize", "column": "num", "params": {"lower_pct": 0.05, "upper_pct": 0.95}}])
    df = pd.read_csv(out)
    assert df["num"].max() < 999


def test_log_transform_handles_non_positive(tmp_path):
    df = base_frame()
    df.loc[0, "num"] = -5.0
    out = str(tmp_path / "out.csv")
    apply_transformations(write_df(tmp_path, df), out,
                          [{"action": "fillna_median", "column": "num"},
                           {"action": "log_transform", "column": "num"}])
    result = pd.read_csv(out)
    assert result["num"].notna().all()
    assert np.isfinite(result["num"].to_numpy()).all()


def test_convert_type_boolean(tmp_path):
    out = str(tmp_path / "out.csv")
    apply_transformations(write_df(tmp_path, base_frame()), out,
                          [{"action": "convert_type", "column": "flag", "params": {"to": "boolean"}}])
    df = pd.read_csv(out)
    assert df["flag"].dtype == bool


def test_convert_type_numeric_reports_failures(tmp_path):
    out = str(tmp_path / "out.csv")
    hist = apply_transformations(write_df(tmp_path, base_frame()), out,
                                 [{"action": "convert_type", "column": "cat", "params": {"to": "numeric"}}])
    assert "NaN" in hist[0]["note"]


def test_unknown_action_raises(tmp_path):
    with pytest.raises(TransformError):
        apply_transformations(write_df(tmp_path, base_frame()), str(tmp_path / "o.csv"),
                              [{"action": "teleport", "column": "num"}])


def test_missing_column_raises(tmp_path):
    with pytest.raises(TransformError):
        apply_transformations(write_df(tmp_path, base_frame()), str(tmp_path / "o.csv"),
                              [{"action": "drop_column", "column": "ghost"}])


def test_preview_does_not_mutate_or_persist(tmp_path):
    src = write_df(tmp_path, base_frame())
    before_content = open(src, "rb").read()
    result = preview_transformations(src, [
        {"action": "fillna_median", "column": "num"},
        {"action": "drop_column", "column": "cat"},
    ], n_preview=5)
    assert result["ok"] is True
    assert result["rows_before"] == result["rows_after"] == 5
    assert any(c["change"] == "removed" and c["column"] == "cat" for c in result["changed_columns"])
    assert len(result["sample_after"][0]) == 2  # cat dropped in preview output
    # Source file untouched
    assert open(src, "rb").read() == before_content


def test_preview_stops_at_first_error(tmp_path):
    result = preview_transformations(write_df(tmp_path, base_frame()), [
        {"action": "fillna_median", "column": "num"},
        {"action": "drop_column", "column": "ghost"},
    ])
    assert result["ok"] is False
    assert "ghost" in result["error"]
    assert len(result["applied_steps"]) == 1  # only the valid step applied


# ──────────────────────────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────────────────────────


async def setup_version(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])
    up = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/upload",
        files={"file": ("data.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    assert up.status_code == 201, up.text
    return project, dataset, up.json()


@pytest.mark.asyncio
async def test_outlier_scan_endpoint(client: AsyncClient, auth_headers: dict):
    project, dataset, version = await setup_version(client, auth_headers)
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version['id']}/outliers",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanned_columns"] >= 2
    cols = {i["column"] for i in body["items"]}
    assert {"age", "age_copy"} <= cols
    for item in body["items"]:
        assert item["recommendation"]["reason"]


@pytest.mark.asyncio
async def test_outlier_detail_all_methods(client: AsyncClient, auth_headers: dict):
    project, dataset, version = await setup_version(client, auth_headers)
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version['id']}/outliers/detail",
        params={"column": "age", "method": "all"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    method_names = {m["method"] for m in body["methods"]}
    assert method_names == {"iqr", "zscore", "isolation_forest", "lof"}
    assert body["histogram"] is not None  # comes from the stored profile
    assert body["recommendation"]["technique"]


@pytest.mark.asyncio
async def test_outlier_detail_rejects_non_numeric(client: AsyncClient, auth_headers: dict):
    project, dataset, version = await setup_version(client, auth_headers)
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version['id']}/outliers/detail",
        params={"column": "gender"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_transform_records_history_and_lineage(client: AsyncClient, auth_headers: dict):
    project, dataset, version = await setup_version(client, auth_headers)

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version['id']}/transform",
        json={"steps": [{"action": "drop_column", "column": "constant"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    new_version = resp.json()
    assert new_version["parent_version_id"] == version["id"]
    assert new_version["transformation_history"][0]["action"] == "drop_column"

    # History chain walks back to original upload
    hist_resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{new_version['id']}/history",
        headers=auth_headers,
    )
    assert hist_resp.status_code == 200
    chain = hist_resp.json()
    assert [c["version_tag"] for c in chain] == [version["version_tag"], new_version["version_tag"]]
    assert chain[0]["steps"] == []  # original upload has no steps


@pytest.mark.asyncio
async def test_preview_transform_endpoint(client: AsyncClient, auth_headers: dict):
    project, dataset, version = await setup_version(client, auth_headers)
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version['id']}/preview-transform",
        json={"steps": [{"action": "drop_column", "column": "constant"}]},
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["columns_after"] == body["columns_before"] - 1


@pytest.mark.asyncio
async def test_compare_versions_endpoint(client: AsyncClient, auth_headers: dict):
    project, dataset, v1 = await setup_version(client, auth_headers)

    tr = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{v1['id']}/transform",
        json={
            "steps": [
                {"action": "drop_column", "column": "constant"},
                {"action": "drop_duplicates", "column": ""},
            ]
        },
        headers=auth_headers,
    )
    v2 = tr.json()

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/compare",
        params={"from_version": v1["id"], "to_version": v2["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_before"] == 100 and body["rows_after"] == 100
    assert body["columns_removed"] == ["constant"]


@pytest.mark.asyncio
async def test_revert_restores_parent_state(client: AsyncClient, auth_headers: dict):
    project, dataset, v1 = await setup_version(client, auth_headers)

    tr = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{v1['id']}/transform",
        json={"steps": [{"action": "drop_column", "column": "constant"}]},
        headers=auth_headers,
    )
    v2 = tr.json()
    assert v2["profile_data"]["num_columns"] == 6

    rv = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{v2['id']}/revert",
        headers=auth_headers,
    )
    assert rv.status_code == 201, rv.text
    v3 = rv.json()
    assert v3["profile_data"]["num_columns"] == 7  # constant restored
    assert v3["parent_version_id"] == v1["id"]

    # Reverting an original upload is rejected
    rv2 = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{v1['id']}/revert",
        headers=auth_headers,
    )
    assert rv2.status_code == 400
