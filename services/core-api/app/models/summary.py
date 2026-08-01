"""Daily-summary aggregate ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base, BaseModel, TenantScopedMixin


class DailySummary(BaseModel, TenantScopedMixin):
    __tablename__ = "daily_summary"
    __pk_name__ = "summary_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'DRAFT'"),
        nullable=False,
    )
    current_version: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SummaryVersion(Base):
    __tablename__ = "summary_version"

    summary_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.daily_summary.summary_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        server_default=sa.text("'{}'"),
        nullable=False,
    )
    model_version: Mapped[str | None] = mapped_column(String(160))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    safety_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.safety_evaluation.safety_evaluation_id"),
    )
    created_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
