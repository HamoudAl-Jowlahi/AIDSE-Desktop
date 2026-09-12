"""
AIDSE Platform — Dataset Ingestion & Profiling Tests (Phase 2)

Covers:
- File format detection & validation
- CSV / XLSX loading
- Schema inference & semantic types
- Missing-value / duplicate / outlier / constant-column detection
- Correlations, target candidate suggestion, class imbalance, leakage
- Upload endpoint behavior (multi-format, validation errors)
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from httpx import AsyncClient

from apps.api.modules.datasets import ingestion
from apps.api.modules.datasets.profiling import profile_dataframe, profile_dataset_file

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def sample_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 100
    age = rng.normal(40, 10, n).round(1)
    return pd.DataFrame(
        {
            "id": range(1, n + 1),
            "age": age,
            "age_copy": age + rng.normal(0, 0.01, n).round(3),
            "gender": rng.choice(["M", "F"], n),
            "signup_date": pd.date_range("2024-01-01", periods=n, freq="D").astype(str),
            "constant": ["X"] * n,
            "target": rng.choice([0, 1], n, p=[0.97, 0.03]),
        }
    )


async def create_project(client: AsyncClient, auth_headers: dict) -> dict:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": f"Ingestion Project {uuid.uuid4().hex[:6]}", "type": "ml"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_dataset(client: AsyncClient, auth_headers: dict, project_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        json={"name": "Test Dataset", "format": "csv"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Format detection & validation
# ──────────────────────────────────────────────────────────────────────────────

def test_detect_format_accepts_supported_extensions():
    assert ingestion.detect_format("data.csv") == ".csv"
    assert ingestion.detect_format("DATA.XLSX") == ".xlsx"
    assert ingestion.detect_format("old_sheet.xls") == ".xls"


@pytest.mark.parametrize("filename", ["report.pdf", "archive.zip", "noext", ""])
def test_detect_format_rejects_unsupported(filename):
    with pytest.raises(ingestion.FileValidationError):
        ingestion.detect_format(filename)


def test_validate_upload_size_rejects_empty():
    with pytest.raises(ingestion.FileValidationError):
        ingestion.validate_upload_size(b"")


def test_validate_upload_size_rejects_oversize(monkeypatch):
    monkeypatch.setattr(ingestion, "MAX_FILE_SIZE_BYTES", 10)
    with pytest.raises(ingestion.FileValidationError):
        ingestion.validate_upload_size(b"x" * 11)


# ──────────────────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────────────────

def test_load_dataframe_csv(tmp_path: Path):
    p = tmp_path / "t.csv"
    p.write_bytes(csv_bytes(sample_frame()))
    df = ingestion.load_dataframe(str(p), ".csv")
    assert df.shape == (100, 7)


def test_load_dataframe_xlsx(tmp_path: Path):
    p = tmp_path / "t.xlsx"
    p.write_bytes(xlsx_bytes(sample_frame()))
    df = ingestion.load_dataframe(str(p), ".xlsx")
    assert df.shape == (100, 7)


def test_load_dataframe_rejects_garbage(tmp_path: Path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"this is not an excel file")
    with pytest.raises(ingestion.FileValidationError):
        ingestion.load_dataframe(str(p), ".xlsx")


# ──────────────────────────────────────────────────────────────────────────────
# Profiling
# ──────────────────────────────────────────────────────────────────────────────

def test_profile_schema_inference_and_semantic_types():
    profile = profile_dataframe(sample_frame())
    cols = profile["columns"]

    assert profile["num_rows"] == 100
    assert profile["num_columns"] == 7
    assert cols["id"]["semantic_type"] == "identifier"
    assert cols["age"]["semantic_type"] == "numeric"
    assert cols["gender"]["semantic_type"] == "categorical"
    assert cols["signup_date"]["semantic_type"] == "datetime"
    assert cols["constant"]["is_constant"] is True


def test_profile_missing_values_detection():
    df = sample_frame()
    df.loc[0:9, "age"] = np.nan
    profile = profile_dataframe(df)
    col = profile["columns"]["age"]
    assert col["null_count"] == 10
    assert col["null_pct"] == 10.0


def test_profile_duplicate_rows_detection():
    df = pd.concat([sample_frame(), sample_frame().head(5)], ignore_index=True)
    profile = profile_dataframe(df)
    assert profile["duplicate_rows"] >= 5


def test_profile_outlier_detection_iqr():
    df = sample_frame()
    df.loc[0, "age"] = 500.0  # extreme outlier vs N(40,10)
    profile = profile_dataframe(df)
    # Outliers counted on raw values; at least the injected one must be caught
    assert profile["columns"]["age"]["outliers_count"] >= 1
    assert "histogram" in profile["columns"]["age"]
    assert len(profile["columns"]["age"]["histogram"]["counts"]) > 0


def test_profile_correlations_surface_strong_pairs():
    profile = profile_dataframe(sample_frame())
    pair = next(
        (p for p in profile["correlations"] if {p["a"], p["b"]} == {"age", "age_copy"}),
        None,
    )
    assert pair is not None
    assert abs(pair["r"]) > 0.99


def test_profile_target_candidate_name_match():
    profile = profile_dataframe(sample_frame())
    candidate = profile["target_candidate"]
    assert candidate is not None
    assert candidate["column"] == "target"
    assert candidate["confidence"] == "name_match"
    assert candidate["task_type"] == "classification"


def test_profile_imbalance_with_explicit_target():
    profile = profile_dataframe(sample_frame(), target_column="target")
    assert profile["imbalance"].get("severity") == "critical"
    dist = profile["imbalance"]["distribution"]
    assert abs(sum(dist.values()) - 1.0) < 0.01


def test_profile_leakage_flags_high_correlation():
    profile = profile_dataframe(sample_frame(), target_column="age")
    leaked = [l["column"] for l in profile["target_leakage"]]
    assert "age_copy" in leaked


def test_profile_quality_issues_summary():
    profile = profile_dataframe(sample_frame())
    summary = profile["quality_issues_summary"]
    assert "critical" in summary and "warning" in summary and "info" in summary
    assert "constant" in summary["constant_columns"]
    assert summary["has_outliers"] is False or isinstance(summary["has_outliers"], bool)


def test_profile_json_safe_output():
    import json

    profile = profile_dataframe(sample_frame())
    # Must serialize without NaN/Infinity leaking through
    serialized = json.dumps(profile)
    assert "NaN" not in serialized
    assert "Infinity" not in serialized


def test_profile_file_entrypoint_csv(tmp_path: Path):
    p = tmp_path / "f.csv"
    p.write_bytes(csv_bytes(sample_frame()))
    profile = profile_dataset_file(str(p))
    assert "error" not in profile
    assert profile["format"] == "csv"
    assert profile["num_columns"] == 7


# ──────────────────────────────────────────────────────────────────────────────
# Upload endpoint
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_csv_returns_ready_profile(
    client: AsyncClient, auth_headers: dict, tmp_path: Path
) -> None:
    project_id = (await create_project(client, auth_headers))["id"]
    dataset_id = (await create_dataset(client, auth_headers, project_id))["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("people.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["profile_status"] == "ready"
    assert data["profile_data"]["num_rows"] == 100
    assert data["profile_data"]["num_columns"] == 7


@pytest.mark.asyncio
async def test_upload_xlsx_converts_and_profiles(
    client: AsyncClient, auth_headers: dict, tmp_path: Path
) -> None:
    project_id = (await create_project(client, auth_headers))["id"]
    dataset_id = (await create_dataset(client, auth_headers, project_id))["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("sheet.xlsx", xlsx_bytes(sample_frame()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["profile_status"] == "ready"
    assert data["profile_data"]["num_rows"] == 100

    # Stored file is normalized to CSV on disk
    assert data["s3_key"].endswith(".csv")


@pytest.mark.asyncio
async def test_upload_unsupported_extension_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    project_id = (await create_project(client, auth_headers))["id"]
    dataset_id = (await create_dataset(client, auth_headers, project_id))["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("evil.exe", b"MZ fake binary", "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    project_id = (await create_project(client, auth_headers))["id"]
    dataset_id = (await create_dataset(client, auth_headers, project_id))["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_corrupt_xlsx_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    project_id = (await create_project(client, auth_headers))["id"]
    dataset_id = (await create_dataset(client, auth_headers, project_id))["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("broken.xlsx", b"PK corrupt payload", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_transform_creates_version_with_profile(
    client: AsyncClient, auth_headers: dict
) -> None:
    project_id = (await create_project(client, auth_headers))["id"]
    dataset_id = (await create_dataset(client, auth_headers, project_id))["id"]

    up = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/upload",
        files={"file": ("people.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    version_id = up.json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/{version_id}/transform",
        json={"steps": [{"action": "drop_column", "column": "constant"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    new_version = resp.json()
    assert new_version["profile_status"] == "ready"
    assert new_version["version_tag"] != up.json()["version_tag"]


# ──────────────────────────────────────────────────────────────────────────────
# Dataset deletion (user-requested feature)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_dataset_removes_rows_and_files(client: AsyncClient, auth_headers: dict):
    import os

    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])

    up = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/upload",
        files={"file": ("people.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    assert up.status_code == 201
    stored_path = up.json()["s3_key"]
    assert os.path.exists(stored_path)

    resp = await client.delete(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert not os.path.exists(stored_path), "physical file must be removed"

    gone = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}",
        headers=auth_headers,
    )
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_delete_dataset_audited(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])

    await client.delete(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}",
        headers=auth_headers,
    )
    logs = await client.get(f"/api/v1/projects/{project['id']}/audit-logs", headers=auth_headers)
    actions = [e["action"] for e in logs.json()]
    assert "dataset.deleted" in actions


@pytest.mark.asyncio
async def test_delete_dataset_cross_tenant_404(client: AsyncClient, auth_headers, second_user_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])

    resp = await client.delete(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}",
        headers=second_user_headers,
    )
    assert resp.status_code in (403, 404)


# ── Regression: string identifier columns must not abort profiling ─────────


def test_profiling_survives_a_string_identifier_column():
    """
    _semantic_type returns "identifier" from its object/string branch for a
    high-cardinality text column, and the profiler then sent it to
    _numeric_stats, whose quantile call raised

        TypeError: unsupported operand type(s) for -: 'str' and 'str'

    deep inside numpy. That aborted the whole profile, so the upload endpoint
    rejected the file with 400. Customer codes, UUIDs, order numbers and
    emails all land in this branch, so most real tabular data could not be
    uploaded at all.
    """
    import pandas as pd

    from apps.api.modules.datasets.profiling import profile_dataframe

    df = pd.DataFrame({
        "customer_id": [f"C{i:04d}" for i in range(60)],       # string identifier
        "order_ref": [f"ORD-{i}-{i*7}" for i in range(60)],    # another one
        "amount": [float(i) * 1.5 for i in range(60)],
        "churned": [i % 2 for i in range(60)],
    })

    profile = profile_dataframe(df)

    assert profile["num_rows"] == 60
    assert profile["num_columns"] == 4

    cid = profile["columns"]["customer_id"]
    assert cid["semantic_type"] == "identifier"
    # No numeric summary for a text key, but it is still described.
    assert "mean" not in cid
    assert cid["unique_count"] == 60

    # A genuinely numeric column still gets its statistics.
    amount = profile["columns"]["amount"]
    assert amount["semantic_type"] == "numeric"
    assert amount["mean"] == pytest.approx(44.25)


def test_numeric_stats_refuses_a_non_numeric_series():
    """The helper guards itself, so one bad classification cannot abort a profile."""
    import pandas as pd

    from apps.api.modules.datasets.profiling import _numeric_stats

    assert _numeric_stats(pd.Series(["a", "b", "c"])) == {}
    assert _numeric_stats(pd.Series([1.0, 2.0, 3.0])) != {}
