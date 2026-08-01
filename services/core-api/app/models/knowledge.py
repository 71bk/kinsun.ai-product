"""Knowledge-source models required by policy provenance foreign keys."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import CHAR, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base, BaseModel, pg_enum
from app.models.outbox import DATA_CLASSIFICATION_ENUM

SOURCE_KIND_ENUM = pg_enum(
    "source_kind_enum",
    "DOCUMENT",
    "WEB_PAGE",
    "DATASET",
    "POLICY",
    "SCALE",
    "MANUAL",
    "OTHER",
)


class KnowledgeSource(BaseModel):
    __tablename__ = "knowledge_source"
    __pk_name__ = "source_id"

    owner_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"),
    )
    registered_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    source_kind: Mapped[str] = mapped_column(SOURCE_KIND_ENUM, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_agency: Mapped[str | None] = mapped_column(String(160))
    public_url: Mapped[str | None] = mapped_column(Text)
    license_status: Mapped[str] = mapped_column(
        String(32),
        server_default=sa.text("'UNKNOWN'"),
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        server_default=sa.text("'NEEDS_REVIEW'"),
        nullable=False,
    )
    data_classification: Mapped[str] = mapped_column(
        DATA_CLASSIFICATION_ENUM,
        server_default=sa.text("'PUBLIC'"),
        nullable=False,
    )


class KnowledgeSourceVersion(Base):
    __tablename__ = "knowledge_source_version"

    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.knowledge_source.source_id"),
        nullable=False,
    )
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.knowledge_source_version.source_version_id"),
    )
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(CHAR(64))
    source_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'DRAFT'"),
        nullable=False,
    )
    uploaded_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
