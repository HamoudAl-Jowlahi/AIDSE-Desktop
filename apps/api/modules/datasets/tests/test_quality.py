"""
AIDSE Platform — Data Quality Center Tests (Phase 3)

Covers:
- Rules engine: every issue category, severity assignment, recommendations
- Legacy/empty profile handling
- API endpoint wiring (incl. pending-profiling state)
"""
from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
import pytest
from httpx import AsyncClient

from apps.api.modules.datasets.profiling import profile_dataframe
from apps.api.modules.datasets.quality import build_quality_report

from apps.api.modules.datasets.tests.test_ingestion import (
    csv_bytes,
    create_dataset,
    create_project,
    sample_frame,
)


def profile_of(df: pd.DataFrame, target: str | None = None) -> dict:
    return profile_dataframe(df, target_column=target)


# ──────────────────────────────────────────────────────────────────────────────
# Rules engine
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_values_issue_with_skewed_recommendation():
    df = sample_frame()
    df.loc[0:19, "age"] = np.nan  # 20% missing
    report = build_quality_report(profile_of(df))
    issue = next(i for i in report["issues"] if i["id"] == "missing:age")
    assert issue["severity"] == "warning"
    assert issue["affected_count"] == 20
    assert issue["affected_pct"] == 20.0
    # age is N(40,10) → roughly symmetric; expect mean-family recommendation
    assert "imputation" in issue["recommendation"]["technique"].lower()
    assert issue["recommendation"]["alternatives"]


def test_missing_values_critical_above_half():
    df = sample_frame()
    df.loc[0:59, "gender"] = None  # 60% missing
    report = build_quality_report(profile_of(df))
    issue = next(i for i in report["issues"] if i["id"] == "missing:gender")
    assert issue["severity"] == "critical"


def test_duplicates_flagged_critical_with_recommendation():
    df = pd.concat([sample_frame(), sample_frame().head(5)], ignore_index=True)
    report = build_quality_report(profile_of(df))
    issue = next(i for i in report["issues"] if i["id"] == "duplicates:rows")
    assert issue["severity"] == "critical"
    assert issue["recommendation"]["technique"]
    assert "why_it_matters" in issue


def test_constant_column_info():
    report = build_quality_report(profile_of(sample_frame()))
    issue = next(i for i in report["issues"] if i["id"] == "constant:constant")
    assert issue["severity"] == "info"
    assert "Drop" in issue["recommendation"]["technique"]


def test_outlier_issue_uses_iqr_method_field():
    df = sample_frame()
    df.loc[0, "age"] = 500.0
    report = build_quality_report(profile_of(df))
    issue = next(i for i in report["issues"] if i["id"] == "outliers:age")
    assert "IQR" in issue["detection_method"]
    assert issue["recommendation"]


def test_high_correlation_pair_detected():
    report = build_quality_report(profile_of(sample_frame()))
    issue = next(
        i for i in report["issues"]
        if i["category"] == "correlations" and set(i["columns"]) == {"age", "age_copy"}
    )
    assert issue["severity"] == "warning"  # r ≈ 1.0 ≥ 0.95
    assert len(issue["columns"]) == 2


def test_target_leakage_critical():
    report = build_quality_report(profile_of(sample_frame(), target="age"))
    leak_issues = [i for i in report["issues"] if i["category"] == "leakage"]
    assert any("age_copy" in i["columns"] for i in leak_issues)
    assert all(i["severity"] == "critical" for i in leak_issues)


def test_class_imbalance_critical_and_metric_advice():
    report = build_quality_report(profile_of(sample_frame(), target="target"))
    issue = next(i for i in report["issues"] if i["category"] == "imbalance")
    assert issue["severity"] == "critical"
    rec = issue["recommendation"]
    assert "weight" in rec["technique"].lower() or "SMOTE" in rec["technique"] or "resampling" in rec["technique"].lower()


def test_identifier_leakage_warning_present():
    report = build_quality_report(profile_of(sample_frame(), target="age"))
    leak_issues = [i for i in report["issues"] if i["category"] == "leakage"]
    assert any("id" in i["columns"] for i in leak_issues)


def test_clean_dataframe_yields_no_issues():
    rng = np.random.default_rng(7)
    n = 200
    df = pd.DataFrame({
        "a": rng.normal(0, 1, n).round(3),
        "b": rng.choice(["x", "y", "z"], n),
        "label": rng.choice([0, 1], n, p=[0.5, 0.5]),
    })
    report = build_quality_report(profile_of(df))
    # No missing, no duplicates, no constants, balanced classes
    cats = {i["category"] for i in report["issues"]}
    assert "missing_values" not in cats
    assert "duplicates" not in cats
    assert "constants" not in cats
    assert "imbalance" not in cats


def test_severity_sorting_order():
    df = sample_frame()
    df.loc[0:9, "age"] = np.nan
    report = build_quality_report(profile_of(df, target="target"))
    severities = [i["severity"] for i in report["issues"]]
    order = {"critical": 0, "warning": 1, "info": 2}
    assert severities == sorted(severities, key=lambda s: order[s])


def test_legacy_or_empty_profile_handled():
    empty = build_quality_report({})
    assert empty["summary"]["available"] is False
    legacy = build_quality_report({"error": "old failure"})
    assert legacy["issues"] == []


def test_every_issue_has_complete_shape():
    df = sample_frame()
    df.loc[0:4, "age"] = np.nan
    report = build_quality_report(profile_of(df, target="target"))
    for issue in report["issues"]:
        assert set(issue) >= {
            "id", "severity", "category", "title", "columns",
            "detection_method", "why_it_matters", "recommendation",
        }
        rec = issue["recommendation"]
        assert set(rec) >= {"technique", "alternatives", "reason", "risk"}


# ──────────────────────────────────────────────────────────────────────────────
# API endpoint
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quality_endpoint_returns_grouped_issues(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])

    up = await client.post(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/upload",
        files={"file": ("people.csv", csv_bytes(sample_frame()), "text/csv")},
        headers=auth_headers,
    )
    version_id = up.json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{version_id}/quality",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["available"] is True
    categories = {i["category"] for i in body["issues"]}
    assert "constants" in categories          # 'constant' column exists
    assert "correlations" in categories       # age/age_copy pair exists
    assert any(i["severity"] == "critical" for i in body["issues"])
    for issue in body["issues"]:
        assert issue["why_it_matters"]
        assert issue["recommendation"]["reason"]


@pytest.mark.asyncio
async def test_quality_endpoint_404_for_unknown_version(client: AsyncClient, auth_headers: dict):
    project = await create_project(client, auth_headers)
    dataset = await create_dataset(client, auth_headers, project["id"])

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset['id']}/versions/{uuid.uuid4()}/quality",
        headers=auth_headers,
    )
    assert resp.status_code == 404
