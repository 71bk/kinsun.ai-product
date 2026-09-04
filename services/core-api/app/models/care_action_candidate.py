"""Human-gated Care Action candidate aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    SCHEMA_NAME,
    BaseModel,
    OptimisticConcurrencyMixin,
    TenantScopedMixin,
    VersionedMixin,
)


class CareActionCandidate(
    BaseModel,
    TenantScopedMixin,
    VersionedMixin,
    OptimisticConcurrencyMixin,
):
    """An AI proposal that is not a formal Care Action until human adoption."""

    __tablename__ = "care_action_candidate"
    __pk_name__ = "care_action_candidate_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    suggested_title: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, server_default="MEDIUM")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING_REVIEW")
    disposition_reason_code: Mapped[str | None] = mapped_column(String(120))
    disposition_notes: Mapped[str | None] = mapped_column(Text)
    decided_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adopted_care_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_action.care_action_id", ondelete="RESTRICT"),
        unique=True,
    )
    extractor_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_event_provenance: Mapped[list[CareActionCandidateEventProvenance]] = relationship(
        back_populates="candidate",
        cascade="save-update, merge",
        lazy="selectin",
        order_by="CareActionCandidateEventProvenance.source_order",
    )


class CareActionCandidateEventProvenance(BaseModel):
    """Append-only source version that justified one candidate."""

    __tablename__ = "care_action_candidate_event_provenance"
    __pk_name__ = "care_action_candidate_event_provenance_id"
    __table_args__ = (
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 15",
            name="ck_care_action_candidate_provenance_order",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_care_action_candidate_provenance_version",
        ),
        sa.CheckConstraint(
            "source_status IN ('VERIFIED','CORRECTED')",
            name="ck_care_action_candidate_provenance_status",
        ),
        sa.CheckConstraint(
            "snapshot_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_care_action_candidate_provenance_sha256",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version = 'care-event-provenance.v1'",
            name="ck_care_action_candidate_provenance_schema",
        ),
        sa.ForeignKeyConstraint(
            ["event_version_id", "event_id", "event_version"],
            [
                f"{SCHEMA_NAME}.care_event_version.event_version_id",
                f"{SCHEMA_NAME}.care_event_version.event_id",
                f"{SCHEMA_NAME}.care_event_version.version",
            ],
            name="fk_care_action_candidate_provenance_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "care_action_candidate_id",
            "source_order",
            name="uq_care_action_candidate_provenance_order",
        ),
        sa.UniqueConstraint(
            "care_action_candidate_id",
            "event_id",
            name="uq_care_action_candidate_provenance_event",
        ),
        sa.UniqueConstraint(
            "care_action_candidate_id",
            "event_version_id",
            name="uq_care_action_candidate_provenance_event_version",
        ),
    )

    care_action_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            f"{SCHEMA_NAME}.care_action_candidate.care_action_candidate_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate: Mapped[CareActionCandidate] = relationship(back_populates="source_event_provenance")
