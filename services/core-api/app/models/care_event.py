"""Care-event aggregate ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base, BaseModel, TenantScopedMixin, pg_enum

REVIEW_DECISION_ENUM = pg_enum(
    "review_decision_enum",
    "VERIFY",
    "CORRECT",
    "REJECT",
    "EXCLUDE",
    "REQUEST_MORE_INFO",
)


class CareEvent(BaseModel, TenantScopedMixin):
    """Care event root; model output can create only candidate states."""

    __tablename__ = "care_event"
    __pk_name__ = "event_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'CANDIDATE'"),
        nullable=False,
    )
    current_version: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )
    consent_version: Mapped[int] = mapped_column(Integer, nullable=False)


class CareEventVersion(Base):
    """Immutable structured content and evidence reference version."""

    __tablename__ = "care_event_version"
    __table_args__ = (
        sa.UniqueConstraint("event_id", "version", name="uq_care_event_version"),
        sa.UniqueConstraint(
            "event_version_id",
            "event_id",
            "version",
            name="uq_care_event_version_identity",
        ),
    )

    event_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_event.event_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    memory_candidate_proposal: Mapped[dict | None] = mapped_column(JSONB)
    evidence_text_ref: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    speaker_role: Mapped[str | None] = mapped_column(String(32))
    speaker_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    speaker_verification_level: Mapped[str | None] = mapped_column(String(32))
    speaker_verification_method: Mapped[str | None] = mapped_column(String(48))
    speaker_evidence_reference: Mapped[str | None] = mapped_column(String(300))
    created_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_event_version.event_version_id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


class ReviewDecision(Base):
    """Append-only human decision and before/after version audit."""

    __tablename__ = "review_decision"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_event.event_id"),
    )
    reviewer_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(REVIEW_DECISION_ENUM, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(120))
    before_version: Mapped[int | None] = mapped_column(Integer)
    after_version: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
