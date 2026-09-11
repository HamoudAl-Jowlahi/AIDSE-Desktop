import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base

if TYPE_CHECKING:
    from apps.api.modules.projects.models import Project


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    format: Mapped[str] = mapped_column(String(50), nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="datasets")
    versions: Mapped[list["DatasetVersion"]] = relationship(
        "DatasetVersion", back_populates="dataset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name!r}>"


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_tag: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    profile_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # pending → profiling queued for a large file; ready → profile_data populated;
    # failed → profiling errored (see profile_data["error"]).
    profile_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Lineage: which version this one was derived from (NULL = original upload)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    # Ordered transformation-step records applied to create this version
    transformation_history: Mapped[list | None] = mapped_column(JSON, nullable=True)

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="versions")

    def __repr__(self) -> str:
        return f"<DatasetVersion id={self.id} tag={self.version_tag!r}>"


class GoldenDataset(Base):
    __tablename__ = "golden_datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )

    project: Mapped["Project"] = relationship("Project", back_populates="golden_datasets")
    cases: Mapped[list["GoldenCase"]] = relationship(
        "GoldenCase", back_populates="golden_dataset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GoldenDataset id={self.id} name={self.name!r} v={self.version}>"


class GoldenCase(Base):
    __tablename__ = "golden_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    golden_dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("golden_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    input_data: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    category_tag: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    golden_dataset: Mapped["GoldenDataset"] = relationship("GoldenDataset", back_populates="cases")

    def __repr__(self) -> str:
        return f"<GoldenCase id={self.id} tag={self.category_tag}>"


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # Fernet-encrypted at rest (core/crypto.py) — never store provider keys in plaintext.
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped["Project"] = relationship("Project")

    def set_api_key(self, plaintext: str) -> None:
        from apps.api.core.crypto import encrypt_value

        self.encrypted_api_key = encrypt_value(plaintext)

    def get_api_key(self) -> str:
        from apps.api.core.crypto import decrypt_value

        return decrypt_value(self.encrypted_api_key)

    def __repr__(self) -> str:
        return f"<ProviderCredential provider={self.provider_name}>"
