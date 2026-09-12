import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from apps.api.core.config import get_settings
import uuid

@pytest.mark.asyncio
async def test_create_and_list_experiments(
    client: AsyncClient,
    logged_in_user: dict,
    auth_headers: dict,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    # 1. Create a Project
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "AutoML Test Project"},
        headers=auth_headers
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 2. Create a Dataset
    ds_resp = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        json={"name": "Housing Data", "format": "csv"},
        headers=auth_headers
    )
    assert ds_resp.status_code == 201
    dataset_id = ds_resp.json()["id"]

    # 3. Create an AutoML Experiment; the router dispatches via Celery's
    #    apply_async (the path production actually takes — it passes
    #    connect_timeout so an unreachable broker fails fast).
    payload = {
        "target_column": "price",
        "problem_type": "regression",
        "primary_metric": "rmse"
    }

    # USE_CELERY defaults to false so desktop installs never probe for a broker;
    # turn it on here because this test is specifically about the dispatch path.
    monkeypatch.setattr(get_settings(), "USE_CELERY", True, raising=False)
    with patch("apps.api.modules.automl.router.run_automl_experiment.apply_async") as mock_dispatch:
        exp_resp = await client.post(
            f"/api/v1/projects/{project_id}/datasets/{dataset_id}/automl/experiments",
            json=payload,
            headers=auth_headers
        )
        assert exp_resp.status_code == 201
        exp_data = exp_resp.json()
        experiment_id = exp_data["id"]

        assert exp_data["target_column"] == "price"
        assert exp_data["problem_type"] == "regression"
        assert exp_data["status"] == "pending"

        mock_dispatch.assert_called_once_with(args=[experiment_id], connect_timeout=1)

    # 4. List Experiments
    list_resp = await client.get(
        f"/api/v1/projects/{project_id}/automl/experiments",
        headers=auth_headers
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == experiment_id

    # 5. Get Experiment details
    get_resp = await client.get(
        f"/api/v1/projects/{project_id}/automl/experiments/{experiment_id}",
        headers=auth_headers
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["id"] == experiment_id
    assert "trials" in get_data
