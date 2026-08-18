"""Confirmed-memory aggregate ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base, BaseModel, TenantScopedMixin


class Memory(BaseModel, TenantScopedMixin):
    __tablename__ = "memory"
    __pk_name__ = "memory_id"
    __table_args__ = (
        sa.CheckConstraint(
            "evidence_state IN ('CURRENT','LEGACY_NEEDS_REVIEW')",
            name="ck_memory_evidence_state",
        ),
        sa.CheckConstraint(
            "evidence_state <> 'LEGACY_NEEDS_REVIEW' " "OR status NOT IN ('ACTIVE','CONFIRMED')",
            name="ck_memory_legacy_not_active",
        ),
        sa.CheckConstraint(
            "(decision_support_profile_id IS NULL) = "
            "(decision_support_profile_version IS NULL) AND "
            "(decision_support_profile_version IS NULL OR "
            "decision_support_profile_version > 0)",
            name="ck_memory_decision_support_profile_binding",
        ),
        sa.ForeignKeyConstraint(
            ["decision_support_profile_id", "decision_support_profile_version"],
            [
                f"{SCHEMA_NAME}.decision_support_profile.decision_support_profile_id",
                f"{SCHEMA_NAME}.decision_support_profile.profile_version",
            ],
            name="fk_memory_decision_support_profile",
        ),
    )

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    memory_kind: Mapped[str | None] = mapped_column(String(48))
    actual_risk_level: Mapped[str | None] = mapped_column(String(16))
    policy_decision: Mapped[str | None] = mapped_column(String(40))
    policy_version: Mapped[str | None] = mapped_column(String(80))
    verification_level: Mapped[str | None] = mapped_column(String(32))
    required_verification: Mapped[str | None] = mapped_column(String(32))
    speaker_verification_level: Mapped[str | None] = mapped_column(String(32))
    speaker_evidence_reference: Mapped[str | None] = mapped_column(String(300))
    evidence_state: Mapped[str] = mapped_column(
        String(32),
        server_default=sa.text("'LEGACY_NEEDS_REVIEW'"),
        nullable=False,
    )
    decision_support_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_support_profile_version: Mapped[int | None] = mapped_column(Integer)
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
    confirmed_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_method: Mapped[str | None] = mapped_column(String(32))
    confirmation_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
    )
    confirmation_evidence_ref: Mapped[str | None] = mapped_column(String(300))
    confirmed_version: Mapped[int | None] = mapped_column(Integer)
    confirmed_content_digest: Mapped[str | None] = mapped_column(String(64))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_reason: Mapped[str | None] = mapped_column(String(120))
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.consent_grant.consent_id"),
    )
    consent_version: Mapped[int] = mapped_column(Integer, nullable=False)


class MemoryVersion(Base):
    __tablename__ = "memory_version"

    memory_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.memory.memory_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_digest: Mapped[str | None] = mapped_column(String(64))
    confirmation_question: Mapped[str | None] = mapped_column(String(300))
    extractor_version: Mapped[str | None] = mapped_column(String(80))
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        server_default=sa.text("'{}'"),
        nullable=False,
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
    )
    source_turn_reference: Mapped[str | None] = mapped_column(String(160))
    proposal_risk_hint: Mapped[str | None] = mapped_column(String(16))
    version_status: Mapped[str] = mapped_column(
        String(16),
        server_default=sa.text("'ACTIVE'"),
        nullable=False,
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.memory_version.memory_version_id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


class MemoryConfirmation(Base):
    """Append-only evidence for one decision about one exact Memory version."""

    __tablename__ = "memory_confirmation"
    __table_args__ = (
        sa.CheckConstraint(
            "memory_version > 0 AND consent_version > 0",
            name="ck_memory_confirmation_positive_versions",
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$'",
            name="ck_memory_confirmation_content_digest",
        ),
        sa.CheckConstraint(
            "confirmation_method IN ('ELDER_UI','ELDER_VOICE','WITNESSED_VOICE')",
            name="ck_memory_confirmation_method",
        ),
        sa.CheckConstraint(
            "response_intent IN ('AFFIRM','REJECT','UNCERTAIN','DEFER')",
            name="ck_memory_confirmation_response_intent",
        ),
        sa.CheckConstraint(
            "speaker_verification_level IN ('VERIFIED_ELDER','WITNESSED_ELDER')",
            name="ck_memory_confirmation_speaker_level",
        ),
        sa.CheckConstraint(
            "(decision_support_profile_id IS NULL) = "
            "(decision_support_profile_version IS NULL) AND "
            "(decision_support_profile_version IS NULL OR "
            "decision_support_profile_version > 0)",
            name="ck_memory_confirmation_profile_binding",
        ),
        sa.ForeignKeyConstraint(
            ["decision_support_profile_id", "decision_support_profile_version"],
            [
                f"{SCHEMA_NAME}.decision_support_profile.decision_support_profile_id",
                f"{SCHEMA_NAME}.decision_support_profile.profile_version",
            ],
            name="fk_memory_confirmation_decision_support_profile",
        ),
        sa.CheckConstraint(
            "(witness_actor_id IS NULL) = (witness_evidence_reference IS NULL)",
            name="ck_memory_confirmation_witness_pair",
        ),
        sa.CheckConstraint(
            "confirmation_method <> 'WITNESSED_VOICE' OR witness_actor_id IS NOT NULL",
            name="ck_memory_confirmation_witnessed_method",
        ),
        sa.UniqueConstraint(
            "memory_id",
            "memory_version",
            "response_intent",
            name="uq_memory_confirmation_version_intent",
        ),
        sa.Index(
            "ix_memory_confirmation_trust_lookup",
            "memory_id",
            "memory_version",
            "content_digest",
            "policy_version",
            "response_intent",
        ),
        sa.Index(
            "ix_memory_confirmation_tenant_elder",
            "tenant_id",
            "elder_id",
            "confirmed_at",
        ),
    )

    memory_confirmation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"),
        nullable=False,
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.memory.memory_id"),
        nullable=False,
    )
    memory_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.consent_grant.consent_id"),
        nullable=False,
    )
    consent_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_support_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_support_profile_version: Mapped[int | None] = mapped_column(Integer)
    confirmation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    response_intent: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmed_by_actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    confirmation_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
    )
    speaker_verification_level: Mapped[str] = mapped_column(String(32), nullable=False)
    speaker_evidence_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    witness_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    witness_evidence_reference: Mapped[str | None] = mapped_column(String(300))
    confirmation_evidence_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
