import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.modules.datasets import models, schemas
from apps.api.modules.projects.models import Project, ProjectMember
import pytest_asyncio

@pytest_asyncio.fixture
async def authorized_client(client: AsyncClient, auth_headers: dict):
    client.headers.update(auth_headers)
    return client

@pytest.fixture
async def test_project(db: AsyncSession, logged_in_user):
    from sqlalchemy import select
    from apps.api.modules.auth.models import User
    
    stmt = select(User).where(User.email == logged_in_user["email"])
    user = (await db.execute(stmt)).scalar_one()

    # Create project
    project = Project(
        name="Dataset Test Project",
        project_type="general",
        owner_id=user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Add user as owner member
    member = ProjectMember(
        project_id=project.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)
    await db.commit()
    return project


@pytest.mark.asyncio
async def test_create_dataset(test_project, authorized_client):
    payload = {
        "name": "Test Dataset",
        "description": "A test dataset",
        "format": "json"
    }
    response = await authorized_client.post(f"/api/v1/projects/{test_project.id}/datasets", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Dataset"
    assert data["format"] == "json"
    assert data["project_id"] == str(test_project.id)
    assert "id" in data


@pytest.mark.asyncio
async def test_list_datasets(test_project, authorized_client, db: AsyncSession):
    # Create dataset directly
    dataset = models.Dataset(
        project_id=test_project.id,
        name="Direct Dataset",
        format="csv"
    )
    db.add(dataset)
    await db.commit()

    response = await authorized_client.get(f"/api/v1/projects/{test_project.id}/datasets")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Direct Dataset"


@pytest.mark.asyncio
async def test_create_dataset_version(test_project, authorized_client, db: AsyncSession):
    # Create dataset directly
    dataset = models.Dataset(
        project_id=test_project.id,
        name="Versioned Dataset",
        format="csv"
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)

    payload = {
        "version_tag": "v1.0",
        "s3_key": "datasets/versioned/v1.0.csv"
    }
    response = await authorized_client.post(f"/api/v1/projects/{test_project.id}/datasets/{dataset.id}/versions", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["version_tag"] == "v1.0"
    assert data["s3_key"] == "datasets/versioned/v1.0.csv"
    assert data["dataset_id"] == str(dataset.id)

@pytest.mark.asyncio
async def test_upload_dataset_file(test_project, authorized_client, db: AsyncSession, tmp_path):
    dataset = models.Dataset(
        project_id=test_project.id,
        name="Upload Dataset",
        format="csv"
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)

    # Create dummy csv file
    csv_content = b"col1,col2,col3\n1,2,3\n4,5,6"
    files = {'file': ('test.csv', csv_content, 'text/csv')}
    
    response = await authorized_client.post(
        f"/api/v1/projects/{test_project.id}/datasets/{dataset.id}/upload", 
        files=files
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["dataset_id"] == str(dataset.id)
    assert data["profile_data"] is not None
    assert data["profile_data"]["num_rows"] == 2
    assert data["profile_data"]["num_columns"] == 3


@pytest.mark.asyncio
async def test_transform_dataset_version(test_project, authorized_client, db: AsyncSession):
    from apps.api.modules.datasets.profiling import profile_dataset_file
    import os
    
    dataset = models.Dataset(project_id=test_project.id, name="Transform Dataset", format="csv")
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    
    # Create a source file
    storage_dir = os.path.join("storage", "datasets", str(test_project.id))
    os.makedirs(storage_dir, exist_ok=True)
    file_path = os.path.join(storage_dir, "test_transform.csv")
    with open(file_path, "w") as f:
        f.write("A,B\n1,2\n3,")
        
    version = models.DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1",
        s3_key=file_path,
        profile_data=profile_dataset_file(file_path)
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    
    payload = {
        "steps": [
            {"action": "fillna_mean", "column": "B"}
        ]
    }
    
    response = await authorized_client.post(
        f"/api/v1/projects/{test_project.id}/datasets/{dataset.id}/versions/{version.id}/transform", 
        json=payload
    )
    assert response.status_code == 201
    data = response.json()
    assert "profile_data" in data
    # The mean of B (2.0) should have filled the missing value.
    # Profile should show 0 nulls for column B.
    assert data["profile_data"]["columns"]["B"]["null_count"] == 0

def test_profile_dataset_file(tmp_path):
    from apps.api.modules.datasets.profiling import profile_dataset_file
    import os
    file_path = os.path.join(tmp_path, "profile_test.csv")
    with open(file_path, "w") as f:
        f.write("target,feature1,feature2\n1,10,A\n1,10,A\n0,20,B\n0,20,B")
    
    profile = profile_dataset_file(file_path, target_column="target")
    assert profile["num_rows"] == 4
    assert profile["num_columns"] == 3
    assert profile["columns"]["target"]["type"] == "int64"
    assert profile["columns"]["feature2"]["unique_count"] == 2