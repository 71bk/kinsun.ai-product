"""Baseline JSONB records plus an explicit immutable v1 API discriminator."""

from datetime import date, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base


class ServiceRecord(Base):
    __tablename__ = "service_record"
    __table_args__ = (
        sa.UniqueConstraint(
            "assignment_id", "service_date", "record_type", name="uq_service_record"
        ),
        sa.Index(
            "uq_service_record_single_note",
            "assignment_id",
            "record_type",
            unique=True,
            postgresql_where=sa.text("version = 1"),
        ),
    )
    service_record_id: Mapped[UUID] = mapped_column(
        sa.UUID(), primary_key=True, server_default=sa.func.gen_random_uuid()
    )
    assignment_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey(f"{SCHEMA_NAME}.care_assignment.assignment_id"), nullable=False
    )
    elder_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"), nullable=False
    )
    worker_id: Mapped[UUID] = mapped_column(
        "worker_actor_id", sa.ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"), nullable=False
    )
    service_date: Mapped[date] = mapped_column(sa.Date(), nullable=False)
    record_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'DRAFT'")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # NULL denotes pre-API rows, never silently promoted or served by v1.
    tenant_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"), nullable=True
    )
    service_timezone: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    version: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    assignment_version: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
