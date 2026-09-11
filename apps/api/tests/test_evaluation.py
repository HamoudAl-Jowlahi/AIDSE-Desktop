import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.modules.evaluation import models as eval_models
from apps.api.modules.datasets import models as ds_models
from apps.api.modules.projects.models import Project, ProjectMember
import pytest_asyncio


@pytest_asyncio.fixture
async def authorized_client(client: AsyncClient, auth_headers: dict):
    client.headers.update(auth_headers)
    return client


@pytest.fixture
async def test_project(db: AsyncSession, logged_in_user):
    from apps.api.modules.auth.models import User
    
    stmt = select(User).where(User.email == logged_in_user["email"])
    user = (await db.execute(stmt)).scalar_one()

    project = Project(
        name="Evaluation Test Project",
        project_type="general",
        owner_id=user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    member = ProjectMember(
        project_id=project.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)
    await db.commit()
    return project


@pytest.fixture
async def golden_dataset(db: AsyncSession, test_project):
    dataset = ds_models.GoldenDataset(
        project_id=test_project.id,
        name="Test Golden Dataset",
        version=1,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    
    case1 = ds_models.GoldenCase(
        golden_dataset_id=dataset.id,
        input_data="input 1",
        expected_output="output 1",
        category_tag="critical",
    )
    case2 = ds_models.GoldenCase(
        golden_dataset_id=dataset.id,
        input_data="input 2",
        expected_output="output 2",
        category_tag="minor",
    )
    db.add_all([case1, case2])
    await db.commit()
    
    from sqlalchemy.orm import selectinload
    stmt = select(ds_models.GoldenDataset).options(selectinload(ds_models.GoldenDataset.cases)).where(ds_models.GoldenDataset.id == dataset.id)
    dataset_with_cases = (await db.execute(stmt)).scalar_one()
    return dataset_with_cases


@pytest.mark.asyncio
async def test_regression_gate(test_project, golden_dataset, authorized_client, db: AsyncSession):
    # 1. Create baseline run manually
    baseline_run = eval_models.EvaluationRun(
        golden_dataset_id=golden_dataset.id,
        provider="test-provider",
        status="completed"
    )
    db.add(baseline_run)
    await db.commit()
    await db.refresh(baseline_run)
    
    cases = golden_dataset.cases
    # Add results for baseline
    res1 = eval_models.EvaluationResult(
        evaluation_run_id=baseline_run.id,
        golden_case_id=cases[0].id,
        actual_output="baseline out 1",
        score=1.0,
        status="pass"
    )
    res2 = eval_models.EvaluationResult(
        evaluation_run_id=baseline_run.id,
        golden_case_id=cases[1].id,
        actual_output="baseline out 2",
        score=1.0,
        status="pass"
    )
    db.add_all([res1, res2])
    await db.commit()
    
    # 2. Set as baseline
    response = await authorized_client.post(
        f"/api/v1/projects/{test_project.id}/datasets/golden-datasets/{golden_dataset.id}/baseline",
        json={"run_id": str(baseline_run.id)}
    )
    assert response.status_code == 200
    
    # 3. Create a new run that regresses
    new_run = eval_models.EvaluationRun(
        golden_dataset_id=golden_dataset.id,
        provider="test-provider",
        status="completed"
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)
    
    new_res1 = eval_models.EvaluationResult(
        evaluation_run_id=new_run.id,
        golden_case_id=cases[0].id,
        actual_output="bad out 1",
        score=0.0,
        status="fail"  # This is the critical case
    )
    new_res2 = eval_models.EvaluationResult(
        evaluation_run_id=new_run.id,
        golden_case_id=cases[1].id,
        actual_output="baseline out 2",
        score=1.0,
        status="pass"
    )
    db.add_all([new_res1, new_res2])
    await db.commit()
    
    # 4. Generate regression report
    response = await authorized_client.post(
        f"/api/v1/projects/{test_project.id}/evaluations/runs/{new_run.id}/regression-report"
    )
    assert response.status_code == 201
    report = response.json()
    assert report["regressed_cases"] == 1
    assert report["critical_regressions"] == 1
    
    # 5. Check CI gate
    gate_response = await authorized_client.get(
        f"/api/v1/projects/{test_project.id}/evaluations/runs/{new_run.id}/gate"
    )
    assert gate_response.status_code == 406
    gate_data = gate_response.json()
    assert gate_data["pass"] is False
    assert gate_data["critical_regressions"] == 1
